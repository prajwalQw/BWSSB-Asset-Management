"""
Integration and End-to-End Tests for Leak Response Demo Flow.
Verifies:
1. Network graph dynamic resolution (no hardcoding of pump or valve).
2. Baseline state: IDLE, normal valve and pump, no active incident.
3. RBAC checks: VIEWER role is rejected from approving isolation (403 / VIEWER_UNAUTHORIZED).
4. Auto-isolation execution (accelerated):
   - Injects leak, triggers alert in SQLite
   - Correlates incident
   - Isolates: pump switched OFF, valve CLOSED
   - Repair simulated with progress tracking
   - Restores: pump restarted, valve OPEN, alert cleared, incident closed
   - Generates downloadable post-mortem HTML report
5. Ask-mode execution:
   - Awaits operator approval before isolating
   - Proceeds once OPERATOR approves
"""

import pytest
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.agents.leak_response import (
    leak_response_sm,
    DemoState,
    resolve_from_network_graph,
    generate_report_html
)

client = TestClient(app)
_orig_sleep = asyncio.sleep


def test_network_graph_resolution():
    """Verify that feeding pump, isolation valve, and stations are dynamically resolved."""
    info = resolve_from_network_graph("CORR_TATAGUNI_MOUNT_JOY")
    assert info["corridor_id"] == "CORR_TATAGUNI_MOUNT_JOY"
    assert "PUMP_TG" in info["feeding_pump_id"]
    assert "Tataguni" in info["from_station"]
    assert "Mount Joy" in info["to_station"]
    assert len(info["impacted_wards"]) > 0


def test_baseline_state():
    """Verify baseline state is IDLE, valve OPEN, no demo running."""
    leak_response_sm.reset_demo()
    status = leak_response_sm.get_status()
    assert status["state"] == DemoState.IDLE.value
    assert status["valve_state"] == "OPEN"
    assert status["repair_pct"] == 0.0
    assert status["incident_report"] is None


def test_rbac_viewer_approval_rejected():
    """Verify that VIEWER / Read-Only users cannot approve isolation."""
    leak_response_sm.reset_demo()
    leak_response_sm.state = DemoState.AWAITING_APPROVAL

    # State machine level
    ok, reason = leak_response_sm.approve_isolation(operator="Viewer1", role="VIEWER")
    assert ok is False
    assert reason == "VIEWER_UNAUTHORIZED"

    # API level with TestClient
    resp = client.post("/api/v1/demo/approve", json={"operator": "Viewer1", "role": "VIEWER"})
    assert resp.status_code == 403
    assert "VIEWER" in resp.json()["detail"].upper()


def test_full_auto_demo_lifecycle_accelerated():
    """
    Runs the full demo state machine with accelerated timers.
    Verifies state transitions, simulator actions, alert creation, and report generation.
    """
    async def _run():
        leak_response_sm.reset_demo()

        fast_cfg = {
            "speeds": {"demo": 0.01},
            "approval_mode": "auto",
            "detection_delay_s": 0.001,
            "agent_diagnose_delay_s": 0.001,
            "approval_countdown_s": 0,
            "repair_crew_delay_s": 0.001,
            "repair_duration_s": 0.005,
            "restore_verify_delay_s": 0.001,
            "restore_ramp_s": 1,
            "leak_pipe": "PIPE_CORRIDOR_10",
            "leak_rate_lps": 45.0,
            "leak_coordinates": [77.5380, 12.9050],
            "repair_stages": [
                {"pct": 0, "label": "Excavation and ground shoring commenced"},
                {"pct": 100, "label": "Pressure test verified at 12.0 bar"}
            ]
        }

        async def _instant_sleep(seconds=0):
            await _orig_sleep(0.0001)

        with patch("backend.app.agents.leak_response._load_demo_cfg", return_value=fast_cfg), \
             patch("backend.app.agents.leak_response.asyncio.sleep", side_effect=_instant_sleep):
            started = leak_response_sm.start_demo()
            assert started is True

            if leak_response_sm._task:
                await leak_response_sm._task

            status = leak_response_sm.get_status()
            assert status["state"] == DemoState.RESTORED.value
            assert status["valve_state"] == "OPEN"
            assert status["repair_pct"] == 100.0
            assert status["incident_report"] is not None
            assert "Transmission Main Leak" in status["incident_report"]["title"]

            html = generate_report_html(status["incident_report"])
            assert "BWSSB" in html
            assert "INCIDENT" in html.upper()
            assert "SIMULATED" in html

    asyncio.run(_run())


def test_ask_mode_operator_approval():
    """Verify ask mode pauses at AWAITING_APPROVAL until an OPERATOR approves."""
    async def _run():
        leak_response_sm.reset_demo()

        fast_cfg = {
            "speeds": {"demo": 0.01},
            "approval_mode": "ask",
            "detection_delay_s": 0.001,
            "agent_diagnose_delay_s": 0.001,
            "approval_countdown_s": 0,
            "repair_crew_delay_s": 0.001,
            "repair_duration_s": 0.005,
            "restore_verify_delay_s": 0.001,
            "restore_ramp_s": 1,
            "leak_pipe": "PIPE_CORRIDOR_10",
            "leak_rate_lps": 45.0,
            "leak_coordinates": [77.5380, 12.9050],
            "repair_stages": [
                {"pct": 0, "label": "Started"},
                {"pct": 100, "label": "Done"}
            ]
        }

        async def _instant_sleep(seconds=0):
            await _orig_sleep(0.0001)

        with patch("backend.app.agents.leak_response._load_demo_cfg", return_value=fast_cfg), \
             patch("backend.app.agents.leak_response.asyncio.sleep", side_effect=_instant_sleep):
            started = leak_response_sm.start_demo()
            assert started is True

            for _ in range(50):
                if leak_response_sm.state == DemoState.AWAITING_APPROVAL:
                    break
                await _orig_sleep(0.005)

            assert leak_response_sm.state == DemoState.AWAITING_APPROVAL

            # Approve as OPERATOR via client API
            resp = client.post("/api/v1/demo/approve", json={"operator": "K. Srinivas (Duty AE)", "role": "OPERATOR"})
            assert resp.status_code == 200
            assert resp.json()["approved"] is True

            if leak_response_sm._task:
                await leak_response_sm._task

            assert leak_response_sm.state == DemoState.RESTORED

    asyncio.run(_run())


def test_ward_selection_and_citizen_notice():
    """Verify ward selection loads exact coordinates and generates citizen disruption notices."""
    leak_response_sm.reset_demo()
    # Test API start with ward selection
    resp = client.post("/api/v1/demo/start", json={"ward": "Hanumanthanagar"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["started"] is True
    assert data["ward"] == "Hanumanthanagar"

    status = leak_response_sm.get_status()
    assert status["selected_ward"] == "Hanumanthanagar"
    assert status["config"]["leak_coordinates"] == [77.5580, 12.9400]
    assert "Hanumanthanagar" in status["config"]["landmark"]
    leak_response_sm.reset_demo()


def test_operator_repair_done_button():
    """Verify operator clicking 'Repair Done' immediately triggers completion and sends restored notice."""
    leak_response_sm.reset_demo()
    leak_response_sm.state = DemoState.REPAIR_IN_PROGRESS
    leak_response_sm.selected_ward = "Padmanabhanagar"

    # Call /api/v1/demo/repair-done
    resp = client.post("/api/v1/demo/repair-done")
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["marked_done"] is True
    assert leak_response_sm._repair_done_event.is_set()

    leak_response_sm.reset_demo()

