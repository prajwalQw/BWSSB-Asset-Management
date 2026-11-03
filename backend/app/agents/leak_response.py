"""
Leak Response State Machine (backend/app/agents/leak_response.py).
Executed by the monitoring agent task. Uses the existing simulator,
alert engine, and audit log. No real device access — bridge stays read-only.

State machine:
  IDLE -> LEAK_INJECTED -> DETECTED -> AGENT_DIAGNOSED -> 
  AWAITING_APPROVAL (ask mode) | COUNTDOWN (auto mode) ->
  ISOLATING -> ISOLATED -> REPAIR_DISPATCHED -> REPAIR_IN_PROGRESS ->
  VERIFYING -> RESTORING -> RESTORED -> IDLE

All timings come from config/demo.yaml (editable without restart).
"""

import asyncio
import time
import logging
import os
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("bwssb.leak_response")

# Lazy imports to avoid circular import at module level
def _get_sim_engine():
    from ..iot.sim.engine import sim_engine
    return sim_engine

def _get_audit_log():
    from ..iot.storage import iot_storage
    return iot_storage


class DemoState(str, Enum):
    IDLE = "IDLE"
    LEAK_INJECTED = "LEAK_INJECTED"
    DETECTED = "DETECTED"
    AGENT_DIAGNOSED = "AGENT_DIAGNOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COUNTDOWN = "COUNTDOWN"
    ISOLATING = "ISOLATING"
    ISOLATED = "ISOLATED"
    REPAIR_DISPATCHED = "REPAIR_DISPATCHED"
    REPAIR_IN_PROGRESS = "REPAIR_IN_PROGRESS"
    VERIFYING = "VERIFYING"
    RESTORING = "RESTORING"
    RESTORED = "RESTORED"


def _load_demo_cfg() -> Dict[str, Any]:
    """Load demo.yaml on every call so live edits take effect without restart."""
    try:
        import yaml
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "demo.yaml")
        with open(os.path.normpath(cfg_path), "r", encoding="utf-8") as f:
            return yaml.safe_load(f).get("demo", {})
    except Exception as e:
        logger.warning(f"Could not load config/demo.yaml: {e}. Using defaults.")
        return {}


def _cfg(key: str, default: Any = None) -> Any:
    return _load_demo_cfg().get(key, default)


WARD_CONFIGS: Dict[str, Dict[str, Any]] = {
    "Basavanagudi": {
        "corridor_id": "CORR_TATAGUNI_MOUNT_JOY",
        "coordinates": [77.5738, 12.9422],
        "landmark": "Pipeline Road Chainage 6+400, Basavanagudi",
        "impacted_wards": ["Basavanagudi", "Hanumanthanagar", "Chamarajpet"],
        "outage_hours": 2,
    },
    "Hanumanthanagar": {
        "corridor_id": "CORR_TATAGUNI_MOUNT_JOY",
        "coordinates": [77.5580, 12.9400],
        "landmark": "50 Feet Main Road Chainage 4+200, Hanumanthanagar",
        "impacted_wards": ["Hanumanthanagar", "Mount Joy Feeder Zone"],
        "outage_hours": 2.5,
    },
    "Chamarajpet": {
        "corridor_id": "CORR_TATAGUNI_MOUNT_JOY",
        "coordinates": [77.5620, 12.9600],
        "landmark": "Bull Temple Road Chainage 7+800, Chamarajpet",
        "impacted_wards": ["Chamarajpet", "Basavanagudi North"],
        "outage_hours": 2,
    },
    "Padmanabhanagar": {
        "corridor_id": "CORR_TATAGUNI_MOUNT_JOY",
        "coordinates": [77.5550, 12.9180],
        "landmark": "Kanakapura Link Chainage 3+100, Padmanabhanagar",
        "impacted_wards": ["Padmanabhanagar", "Uttarahalli Main"],
        "outage_hours": 3,
    },
}


def resolve_from_network_graph(corridor_id: str = "CORR_TATAGUNI_MOUNT_JOY", ward: Optional[str] = None) -> Dict[str, Any]:
    """
    Dynamically resolves the feeding pump, isolation valve, and downstream impact
    from the network graph configuration files and selected ward rather than hardcoding.
    """
    target_ward = ward if ward in WARD_CONFIGS else "Basavanagudi"
    w_info = WARD_CONFIGS[target_ward]
    corridor_id = w_info.get("corridor_id", corridor_id)
    leak_coordinates = w_info["coordinates"]
    landmark = w_info["landmark"]
    impacted_wards = w_info["impacted_wards"]
    outage_hours = w_info["outage_hours"]

    root_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    network_flows_path = os.path.join(root_dir, "config", "iot", "network_flows.yaml")
    stations_path = os.path.join(root_dir, "config", "iot", "stations.yaml")
    sim_zone_path = os.path.join(root_dir, "config", "simulated_zone.yaml")

    feeding_pump_id = "PUMP_TG_H1"
    feeding_pump_name = "High-Lift Pump 1 (TG-HLP-01)"
    isolation_valve_name = "BFV-104 (Motorised Butterfly Valve)"
    from_station = "Tataguni Terminal Pumping Station"
    to_station = "Mount Joy GLR"
    alternate_source = "Harohalli Stage V via High Grounds GLR"
    alternate_coverage_pct = 65
    alternate_coverage_hours = 4

    try:
        import yaml
        if os.path.exists(network_flows_path):
            with open(network_flows_path, "r", encoding="utf-8") as f:
                flows = yaml.safe_load(f)
                for corr in flows.get("transmission_corridors", []):
                    if corr.get("id") == corridor_id:
                        from_node = corr.get("from_node", "WTP_TATAGUNI")
                        to_node = corr.get("to_node", "GLR_MOUNT_JOY")
                        from_station = from_node.replace("WTP_", "").replace("_", " ").title() + " Terminal Complex"
                        to_station = to_node.replace("GLR_", "").replace("_", " ").title() + " GLR"
                        break

        if os.path.exists(stations_path):
            with open(stations_path, "r", encoding="utf-8") as f:
                stns_data = yaml.safe_load(f)
                for s in stns_data.get("stations", []):
                    if "TATAGUNI" in s.get("id", "").upper():
                        from_station = s.get("name", from_station)
                        pumps = s.get("pumps", [])
                        for p in pumps:
                            if p.get("class") == "high-lift" or "high-lift" in p.get("name", "").lower():
                                feeding_pump_id = p.get("id", feeding_pump_id)
                                feeding_pump_name = f"{p.get('name', 'High-Lift Pump 1')} ({p.get('tag', 'TG-HLP-01')})"
                                break

        if os.path.exists(sim_zone_path):
            with open(sim_zone_path, "r", encoding="utf-8") as f:
                zone_data = yaml.safe_load(f)
                for v in zone_data.get("valves", []):
                    if "104" in v.get("name", "") or "BVG" in v.get("id", ""):
                        isolation_valve_name = v.get("name", isolation_valve_name)
                        break
    except Exception as ex:
        logger.warning(f"Error resolving from network graph: {ex}. Using graph-anchored defaults.")

    return {
        "ward": target_ward,
        "corridor_id": corridor_id,
        "leak_coordinates": leak_coordinates,
        "landmark": landmark,
        "feeding_pump_id": feeding_pump_id,
        "feeding_pump_name": feeding_pump_name,
        "isolation_valve_name": isolation_valve_name,
        "from_station": from_station,
        "to_station": to_station,
        "impacted_wards": impacted_wards,
        "outage_hours": outage_hours,
        "alternate_source": alternate_source,
        "alternate_coverage_pct": alternate_coverage_pct,
        "alternate_coverage_hours": alternate_coverage_hours,
    }


class LeakResponseStateMachine:
    """
    Self-contained demo state machine.
    Call start_demo() to kick off; the asyncio task drives the states.
    All side effects on simulator are SIMULATED only.
    """

    def __init__(self):
        self.state: DemoState = DemoState.IDLE
        self.state_entered_at: float = time.time()
        self.demo_started_at: Optional[float] = None
        self.alert_id: Optional[str] = None
        self.incident_id: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._approval_event: asyncio.Event = asyncio.Event()
        self._repair_done_event: asyncio.Event = asyncio.Event()
        self._cancelled: bool = False

        # Selected ward & citizen notice state
        self.selected_ward: str = "Basavanagudi"
        self.ward_notice: Optional[Dict[str, Any]] = None

        # Physical simulator state modifications
        self.valve_state: str = "OPEN"
        self.isolated_pump_id: Optional[str] = None

        # Step log: [{label, ts, elapsed_s}]
        self.step_log: List[Dict[str, Any]] = []

        # Accumulated metrics for report
        self.volume_lost_kl: float = 0.0
        self.energy_saved_kwh: float = 0.0
        self.pump_stop_time: Optional[float] = None
        self.pump_restart_time: Optional[float] = None
        self.approval_operator: Optional[str] = None

        # Dynamic graph resolution
        self.graph_info: Dict[str, Any] = resolve_from_network_graph(ward=self.selected_ward)

        # Exposed state (for API)
        self.agent_response: Dict[str, Any] = {}
        self.repair_pct: float = 0.0
        self.repair_eta_s: float = 0.0
        self.incident_report: Optional[Dict[str, Any]] = None

    # ─── Public API ─────────────────────────────────────────────────────────

    def start_demo(self, ward: str = "Basavanagudi") -> bool:
        """Inject leak and start the async state machine for the selected ward."""
        if self.state not in (DemoState.IDLE, DemoState.RESTORED):
            return False
        self._cancelled = False
        self._approval_event.clear()
        self._repair_done_event.clear()
        if ward not in WARD_CONFIGS:
            ward = "Basavanagudi"
        self.selected_ward = ward
        self.graph_info = resolve_from_network_graph(ward=ward)
        self.valve_state = "OPEN"
        self.ward_notice = None
        self._task = asyncio.create_task(self._run())
        return True

    def mark_repair_done(self) -> bool:
        """Allows operator to click 'Repair Done' during repair stages to restore water."""
        if self.state in (DemoState.REPAIR_DISPATCHED, DemoState.REPAIR_IN_PROGRESS):
            self._repair_done_event.set()
            self._log_step(f"Operator confirmed: Pipe repair completed for {self.selected_ward}")
            return True
        return False

    def reset_demo(self):
        """Cancel the state machine and return everything to baseline."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()
        self._repair_done_event.set()
        self._do_reset()
        self._set_state(DemoState.IDLE)
        self.valve_state = "OPEN"
        self.step_log = []
        self.repair_pct = 0.0
        self.repair_eta_s = 0.0
        self.agent_response = {}
        self.incident_report = None
        self.ward_notice = None
        self.volume_lost_kl = 0.0
        self.energy_saved_kwh = 0.0
        self.pump_stop_time = None
        self.pump_restart_time = None
        self.approval_operator = None
        self.alert_id = None
        self.incident_id = None
        self._log_step("Demo reset: system returned to normal baseline")
        logger.info("[LeakDemo] Demo reset to IDLE.")

    def approve_isolation(self, operator: str = "OPERATOR", role: str = "OPERATOR") -> Tuple[bool, str]:
        """Called by operator to approve isolation in 'ask' mode."""
        if role.upper() in ("VIEWER", "READ_ONLY", "ANONYMOUS"):
            logger.warning(f"Role {role} unauthorized to approve isolation")
            return False, "VIEWER_UNAUTHORIZED"

        if self.state != DemoState.AWAITING_APPROVAL:
            return False, f"INVALID_STATE_{self.state.value}"

        self.approval_operator = operator
        self._approval_event.set()
        self._log_step(f"Isolation approved by {operator} (Role: {role})")
        return True, "APPROVED"

    def reject_isolation(self, operator: str = "OPERATOR", role: str = "OPERATOR") -> Tuple[bool, str]:
        """Called by operator to reject isolation in 'ask' mode."""
        if role.upper() in ("VIEWER", "READ_ONLY", "ANONYMOUS"):
            return False, "VIEWER_UNAUTHORIZED"

        if self.state != DemoState.AWAITING_APPROVAL:
            return False, f"INVALID_STATE_{self.state.value}"

        self._log_step(f"Isolation REJECTED by {operator} (Role: {role})")
        self._cancelled = True
        self._do_reset()
        self._set_state(DemoState.IDLE)
        return True, "REJECTED"

    def get_status(self) -> Dict[str, Any]:
        elapsed = round(time.time() - self.demo_started_at, 1) if self.demo_started_at else 0.0
        return {
            "state": self.state.value,
            "state_entered_at": self.state_entered_at,
            "demo_started_at": self.demo_started_at,
            "elapsed_s": elapsed,
            "alert_id": self.alert_id,
            "incident_id": self.incident_id,
            "step_log": self.step_log,
            "agent_response": self.agent_response,
            "valve_state": self.valve_state,
            "repair_pct": round(self.repair_pct, 1),
            "repair_eta_s": round(self.repair_eta_s, 1),
            "incident_report": self.incident_report,
            "approval_mode": _cfg("approval_mode", "auto"),
            "selected_ward": self.selected_ward,
            "available_wards": list(WARD_CONFIGS.keys()),
            "ward_notice": self.ward_notice,
            "config": {
                "pipe_segment_id": self.graph_info["corridor_id"],
                "feeding_pump_id": self.graph_info["feeding_pump_id"],
                "feeding_pump_name": self.graph_info["feeding_pump_name"],
                "isolation_valve_name": self.graph_info["isolation_valve_name"],
                "from_station": self.graph_info["from_station"],
                "to_station": self.graph_info["to_station"],
                "leak_rate_lps": _cfg("leak_rate_lps", 45.0),
                "leak_coordinates": self.graph_info.get("leak_coordinates", [77.5380, 12.9050]),
                "landmark": self.graph_info.get("landmark", "Pipeline Road Chainage 6+400"),
                "impacted_wards": self.graph_info["impacted_wards"],
                "outage_hours": self.graph_info.get("outage_hours", 2),
                "alternate_source": self.graph_info["alternate_source"],
                "alternate_coverage_pct": self.graph_info["alternate_coverage_pct"],
                "alternate_coverage_hours": self.graph_info["alternate_coverage_hours"],
            },
            "data_tier": "SIMULATED",
            "disclaimer": "Automatic isolation is simulated. Real field control is not enabled.",
        }

    # ─── State Machine ───────────────────────────────────────────────────────

    async def _run(self):
        try:
            await self._state_inject()
            if self._cancelled: return
            await self._state_detect()
            if self._cancelled: return
            await self._state_diagnose()
            if self._cancelled: return
            await self._state_approval()
            if self._cancelled: return
            await self._state_isolate()
            if self._cancelled: return
            await self._state_repair()
            if self._cancelled: return
            await self._state_restore()
        except asyncio.CancelledError:
            logger.info("[LeakDemo] Demo task cancelled.")
        except Exception as e:
            logger.error(f"[LeakDemo] Unexpected error: {e}", exc_info=True)

    async def _state_inject(self):
        cfg = _load_demo_cfg()
        self.demo_started_at = time.time()
        self._set_state(DemoState.LEAK_INJECTED)
        sim = _get_sim_engine()
        leak_rate = cfg.get("leak_rate_lps", 45.0)
        seg_id = self.graph_info["corridor_id"]
        landmark = self.graph_info.get("landmark", "Pipeline Road Chainage 6+400")
        # Use existing simulator leak injection
        sim.inject_leak(seg_id, leak_rate, landmark=landmark)
        self._log_step(f"Leak injected: {leak_rate} L/s on {seg_id} in {self.selected_ward} ({landmark})")
        logger.info(f"[LeakDemo] Leak injected at {leak_rate} L/s on segment {seg_id} ({self.selected_ward})")

    async def _state_detect(self):
        cfg = _load_demo_cfg()
        delay = cfg.get("detection_delay_s", 10)
        await asyncio.sleep(delay)
        if self._cancelled: return

        self._set_state(DemoState.DETECTED)
        sim = _get_sim_engine()
        # Find the leak alert raised by the mass-balance detector
        for _ in range(5):
            sim.tick(1.0)
        alert = None
        for a in sim.alerts.values():
            if a.active and ("leak" in a.title.lower() or a.category == "HYDRAULIC_INTEGRITY"):
                alert = a
                break
        if alert:
            self.alert_id = alert.alert_id
            self._log_step(f"Alert raised: {alert.alert_id} — {alert.title}")
            logger.info(f"[LeakDemo] Detected alert: {alert.alert_id}")
        else:
            self.alert_id = "ALT-LEAK-CORR_TATAGUNI_MOUNT_JOY"
            self._log_step("Alert raised: ALT-LEAK-CORR_TATAGUNI_MOUNT_JOY — Transmission Line Mass Balance Deficit")

    async def _state_diagnose(self):
        cfg = _load_demo_cfg()
        delay = cfg.get("agent_diagnose_delay_s", 3)
        await asyncio.sleep(delay)
        if self._cancelled: return

        self._set_state(DemoState.AGENT_DIAGNOSED)
        self.incident_id = f"INC-DEMO-{int(time.time()) % 10000:04d}"

        pump_name = self.graph_info["feeding_pump_name"]
        valve_name = self.graph_info["isolation_valve_name"]
        wards = self.graph_info["impacted_wards"]
        alt_src = self.graph_info["alternate_source"]
        alt_pct = self.graph_info["alternate_coverage_pct"]
        alt_hrs = self.graph_info["alternate_coverage_hours"]

        self.agent_response = {
            "incident_id": self.incident_id,
            "steps": [
                {
                    "label": "Leak confirmed by pressure drop and flow imbalance",
                    "ts": time.strftime("%H:%M:%S"),
                    "done": True,
                },
                {
                    "label": f"Proposed action: switch OFF {pump_name} and close isolation valve {valve_name} to stop supply into the leaking section",
                    "ts": time.strftime("%H:%M:%S"),
                    "done": True,
                },
                {
                    "label": (
                        f"Impact if isolated: wards {', '.join(wards)} lose supply from this line; "
                        f"fallback: {alt_src} covers {alt_pct}% for {alt_hrs} hours (Simulated)"
                    ),
                    "ts": time.strftime("%H:%M:%S"),
                    "done": True,
                },
            ],
            "approval_mode": cfg.get("approval_mode", "auto"),
            "disclaimer": "Automatic isolation is simulated. Real field control is not enabled.",
        }
        self._log_step(f"Agent opened incident {self.incident_id}: correlated leak + pressure drop + tank drawdown")
        logger.info(f"[LeakDemo] Agent diagnosed: incident {self.incident_id}")

    async def _state_approval(self):
        cfg = _load_demo_cfg()
        mode = cfg.get("approval_mode", "auto")

        if mode == "ask":
            self._set_state(DemoState.AWAITING_APPROVAL)
            self._log_step("Awaiting operator approval for isolation")
            self.agent_response["countdown"] = None
            # Wait for operator to approve or reject
            await self._approval_event.wait()
            if self._cancelled: return
        else:
            # Auto mode: countdown
            countdown_s = int(cfg.get("approval_countdown_s", 3))
            self._set_state(DemoState.COUNTDOWN)
            for remaining in range(countdown_s, 0, -1):
                self.agent_response["countdown"] = remaining
                await asyncio.sleep(1.0)
                if self._cancelled: return
            self.agent_response["countdown"] = 0
            self._log_step(f"Auto-approval: isolating after {countdown_s}s countdown")

    async def _state_isolate(self):
        self._set_state(DemoState.ISOLATING)
        cfg = _load_demo_cfg()
        pump_id = self.graph_info["feeding_pump_id"]
        seg_id = self.graph_info["corridor_id"]
        valve_name = self.graph_info["isolation_valve_name"]
        sim = _get_sim_engine()
        storage = _get_audit_log()

        self.isolated_pump_id = pump_id

        # 1. Stop the pump via simulator state
        stn = sim.stations_state.get("PS_TATAGUNI", {})
        pdata = stn.get("pumps", {}).get(pump_id)
        if pdata:
            pdata["state"] = "STOPPING"
            pdata["state_timer_s"] = 0.0
            pdata["isolated_by_agent"] = True
            pdata["lock_tag"] = "AGENT_ISOLATION_LOCK"
            self._log_step(f"Pump {pump_id} -> STOPPING (ramp down initiated)")
        else:
            self._log_step(f"Pump {pump_id} set to STOPPING")

        # 2. Close isolation valve
        self.valve_state = "CLOSED"
        self._log_step(f"Isolation valve {valve_name} -> CLOSED")

        # 3. Write audit log
        storage.save_injection(
            "isolation_action",
            pump_id,
            {
                "action": "PUMP_STOP_ISOLATION",
                "pump_id": pump_id,
                "valve": valve_name,
                "segment": seg_id,
                "operator": self.approval_operator or "AUTOMATIC_MONITOR_AGENT",
                "approval_mode": cfg.get("approval_mode", "auto"),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "simulated": True,
            },
            active=True,
        )

        # 4. Wait for pump to reach OFF (simulated stop ramp)
        await asyncio.sleep(6.0)
        if self._cancelled: return
        if pdata:
            pdata["state"] = "OFF"
            pdata["current_r"] = 0.0
            pdata["current_y"] = 0.0
            pdata["current_b"] = 0.0
            pdata["current_avg"] = 0.0
            pdata["active_power_kw"] = 0.0
            pdata["flow_lps"] = 0.0
            pdata["isolated_by_agent"] = True
            self.pump_stop_time = time.time()
            self._log_step(f"Pump {pump_id} -> OFF - isolated by monitoring agent [LOCK]")

            # Generate Public Citizen Notice for the affected ward
            now_dt = datetime.now()
            start_t = now_dt.strftime("%I:%M %p")
            end_t = (now_dt + timedelta(hours=self.graph_info.get("outage_hours", 2))).strftime("%I:%M %p")
            landmark = self.graph_info.get("landmark", "Pipeline Road Chainage 6+400")
            self.ward_notice = {
                "status": "DISRUPTED",
                "ward": self.selected_ward,
                "landmark": landmark,
                "time_from": start_t,
                "time_to": end_t,
                "title": f"BWSSB Citizen Notice — Water Disruption in {self.selected_ward}",
                "message": f"Notice to residents of {self.selected_ward}: There is a pipeline leakage in this area at {landmark}, so emergency repair work is underway. Water will not be available from {start_t} to {end_t}. Sorry for the inconvenience caused, please cooperate with us.",
                "timestamp": time.strftime("%I:%M %p"),
            }
            self._log_step(f"Citizen alert broadcast sent to residents of {self.selected_ward} (Outage: {start_t} - {end_t})")

        # 5. Section flow -> 0, leak loss decays to 0 as section depressurises
        for _ in range(4):
            lk = sim.active_injections.get("leak")
            if lk:
                lk["leak_rate_lps"] = max(0.0, lk["leak_rate_lps"] * 0.4)
            await asyncio.sleep(1.0)
        if sim.active_injections.get("leak"):
            sim.active_injections["leak"]["leak_rate_lps"] = 0.0

        self._set_state(DemoState.ISOLATED)
        self._log_step("Isolation complete: pipe depressurised, leak loss -> 0 L/s")

    async def _state_repair(self):
        cfg = _load_demo_cfg()
        crew_delay = cfg.get("repair_crew_delay_s", 20)
        repair_dur = cfg.get("repair_duration_s", 20)

        self._set_state(DemoState.REPAIR_DISPATCHED)
        landmark = self.graph_info.get("landmark", "Pipeline Road Chainage 6+400")
        self._log_step(f"Repair crew dispatched to {landmark}")
        
        # Crew dispatch delay (or immediate if operator presses repair done)
        crew_start = time.time()
        while time.time() - crew_start < crew_delay:
            if self._repair_done_event.is_set():
                break
            await asyncio.sleep(0.5)
            if self._cancelled: return

        self._set_state(DemoState.REPAIR_IN_PROGRESS)
        self._log_step(f"Repair in progress: pipe excavation and sleeve clamp replacement at {landmark}")
        start = time.time()
        while True:
            elapsed = time.time() - start
            self.repair_pct = min(100.0, (elapsed / repair_dur) * 100.0)
            self.repair_eta_s = max(0.0, repair_dur - elapsed)
            if elapsed >= repair_dur or self._repair_done_event.is_set():
                break
            await asyncio.sleep(0.5)
            if self._cancelled: return

        self.repair_pct = 100.0
        self.repair_eta_s = 0.0
        self._log_step("Leak repaired: structural pipe joint replaced and sealed")

    async def _state_restore(self):
        cfg = _load_demo_cfg()
        verify_delay = cfg.get("restore_verify_delay_s", 5)
        ramp_s = cfg.get("restore_ramp_s", 10)
        pump_id = self.graph_info["feeding_pump_id"]
        valve_name = self.graph_info["isolation_valve_name"]
        sim = _get_sim_engine()

        self._set_state(DemoState.VERIFYING)
        self._log_step("Pre-start verification check: hydrostatic pressure hold test")
        await asyncio.sleep(verify_delay)
        if self._cancelled: return
        self._log_step("Pressure test PASSED: hydraulic integrity confirmed, zero imbalance")

        # Stop leak injection entirely
        corridor_id = self.graph_info.get("corridor_id", "CORR_TG_MJ")
        sim.stop_leak(corridor_id)
        if corridor_id != "CORR_TG_MJ":
            sim.stop_leak("CORR_TG_MJ")
        self._log_step("Leak cleared: mass balance detector returns to nominal")

        # Reopen isolation valve
        self.valve_state = "OPEN"
        self._log_step(f"Isolation valve {valve_name} -> REOPENED")

        # Restart the pump through normal start profile
        self._set_state(DemoState.RESTORING)
        stn = sim.stations_state.get("PS_TATAGUNI", {})
        pdata = stn.get("pumps", {}).get(pump_id)
        if pdata:
            pdata["state"] = "STARTING"
            pdata["state_timer_s"] = 0.0
            pdata["start_elapsed_s"] = 0.0
            pdata["starts_count"] = pdata.get("starts_count", 0) + 1
            pdata.pop("isolated_by_agent", None)
            pdata.pop("lock_tag", None)
            fla = pdata["cfg"].get("rated_fla_a", 124.5)
            k = pdata["cfg"].get("inrush_factor_k", 2.0)
            pdata["inrush_peak_a"] = round(fla * k, 1)
            pdata["current_avg"] = round(fla * k, 1)
            pdata["current_r"] = pdata["current_avg"]
            pdata["current_y"] = pdata["current_avg"]
            pdata["current_b"] = pdata["current_avg"]
            self._log_step(f"Pump {pump_id} -> STARTING (inrush current spike: {pdata['inrush_peak_a']} A)")

        # Ramp current to plateau
        for i in range(ramp_s):
            elapsed_frac = (i + 1) / ramp_s
            if pdata:
                fla = pdata["cfg"].get("rated_fla_a", 124.5)
                k = pdata["cfg"].get("inrush_factor_k", 2.0)
                inrush_decay = (1.0 - elapsed_frac) * fla * (k - 1.0)
                pdata["current_avg"] = round(fla + inrush_decay, 1)
                pdata["current_r"] = pdata["current_avg"]
                pdata["current_y"] = pdata["current_avg"]
                pdata["current_b"] = pdata["current_avg"]
                rated_flow = pdata["cfg"].get("pump_curve", {}).get("flow_lps_rated", 888.89)
                pdata["flow_lps"] = round(rated_flow * elapsed_frac * 0.9, 1)
            await asyncio.sleep(1.0)
            if self._cancelled: return

        # Fully RUNNING
        if pdata:
            fla = pdata["cfg"].get("rated_fla_a", 124.5)
            pdata["state"] = "RUNNING"
            pdata["current_avg"] = round(fla * 0.87, 1)
            pdata["current_r"] = pdata["current_avg"]
            pdata["current_y"] = pdata["current_avg"]
            pdata["current_b"] = pdata["current_avg"]
            rated_flow = pdata["cfg"].get("pump_curve", {}).get("flow_lps_rated", 888.89)
            pdata["flow_lps"] = round(rated_flow * 0.88, 1)
            pdata["active_power_kw"] = round(
                1.732 * pdata["cfg"].get("rated_voltage_v", 6600) * pdata["current_avg"] * 0.88 / 1000.0, 1
            )
            self.pump_restart_time = time.time()
            self._log_step(f"Pump {pump_id} -> RUNNING (steady current plateau: {pdata['current_avg']} A)")

        # Clear leak alert from active alerts
        if self.alert_id and self.alert_id in sim.alerts:
            sim.clear_alert(self.alert_id)
            self._log_step(f"Alert {self.alert_id} cleared and archived to history")

        # Build incident closure report
        now = time.time()
        started = self.demo_started_at or now
        duration_min = round((now - started) / 60, 1)
        leak_rate = cfg.get("leak_rate_lps", 45.0)
        self.volume_lost_kl = round(leak_rate * (now - started) * 0.001, 1)
        self.energy_saved_kwh = round((duration_min / 60.0) * 1200.0 * 0.4, 1)

        # Broadcast Citizen Water Restored Notice
        landmark = self.graph_info.get("landmark", "Pipeline Road Chainage 6+400")
        self.ward_notice = {
            "status": "RESTORED",
            "ward": self.selected_ward,
            "landmark": landmark,
            "title": f"BWSSB Notice: Water Supply Restored in {self.selected_ward}",
            "message": f"Notice to residents of {self.selected_ward}: Emergency pipeline repair at {landmark} has been successfully completed. Water supply has been restored. Thank you for your cooperation, you can use water now.",
            "timestamp": time.strftime("%I:%M %p"),
        }
        self._log_step(f"Citizen restoration broadcast sent to residents of {self.selected_ward}")

        self.incident_report = {
            "incident_id": self.incident_id,
            "title": f"Transmission Main Leak — {self.graph_info['from_station']} to {self.graph_info['to_station']}",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_min": duration_min,
            "volume_lost_kl": self.volume_lost_kl,
            "energy_saved_kwh": self.energy_saved_kwh,
            "approval_mode": cfg.get("approval_mode", "auto"),
            "approved_by": self.approval_operator or ("AUTOMATIC (Supervisor)" if cfg.get("approval_mode") == "auto" else "OPERATOR"),
            "actions_taken": [s["label"] for s in self.step_log],
            "timeline": self.step_log,
            "data_tier": "SIMULATED",
            "disclaimer": "Automatic isolation is simulated. Real field control is not enabled.",
        }

        self._set_state(DemoState.RESTORED)
        self._log_step("Incident closed: flows, pressures and Mount Joy GLR storage recovering to baseline")
        logger.info("[LeakDemo] Demo complete: RESTORED")

    # ─── Report Generator ───────────────────────────────────────────────────

    def generate_report_html(self) -> str:
        rep = self.incident_report or {
            "incident_id": self.incident_id or "INC-DEMO-BASAL",
            "title": f"Transmission Main Leak — {self.graph_info['from_station']} to {self.graph_info['to_station']}",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.demo_started_at or time.time())),
            "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_min": 1.5,
            "volume_lost_kl": self.volume_lost_kl or 54.0,
            "energy_saved_kwh": 32.5,
            "approved_by": self.approval_operator or "AUTOMATIC (Supervisor)",
            "approval_mode": _cfg("approval_mode", "auto"),
            "actions_taken": [s["label"] for s in self.step_log],
            "timeline": self.step_log,
        }

        timeline_rows = "".join(
            f"<tr><td style='padding:6px 10px; border-bottom:1px solid #e2e8f0; font-family:monospace; color:#475569;'>{s.get('ts')}</td>"
            f"<td style='padding:6px 10px; border-bottom:1px solid #e2e8f0; font-family:monospace; color:#0284c7;'>+{s.get('elapsed_s')}s</td>"
            f"<td style='padding:6px 10px; border-bottom:1px solid #e2e8f0;'>{s.get('label')}</td></tr>"
            for s in rep.get("timeline", self.step_log)
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BWSSB Incident Closure Report - {rep['incident_id']}</title>
<style>
  @page {{ size: A4 portrait; margin: 15mm; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #0f172a; margin: 0; padding: 24px; background: #fff; line-height: 1.45; font-size: 13px; }}
  .header {{ border-bottom: 3px solid #0284c7; padding-bottom: 12px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: flex-end; }}
  .chip {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; font-family: monospace; text-transform: uppercase; }}
  .chip-sim {{ background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }}
  .chip-crit {{ background: #ffe4e6; color: #be123c; border: 1px solid #fecdd3; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
  .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; }}
  .label {{ font-size: 10px; text-transform: uppercase; color: #64748b; font-family: monospace; display: block; }}
  .val {{ font-size: 16px; font-weight: 700; color: #0f172a; margin-top: 2px; font-family: monospace; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }}
  th {{ background: #f1f5f9; padding: 8px 10px; text-align: left; font-size: 11px; text-transform: uppercase; color: #475569; border-bottom: 2px solid #cbd5e1; }}
  .disclaimer {{ margin-top: 20px; padding: 10px 14px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; color: #991b1b; font-size: 11px; }}
  .print-btn {{ background: #0284c7; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; }}
  @media print {{ .no-print {{ display: none !important; }} body {{ padding: 0; }} }}
</style>
</head>
<body>
<div class="no-print" style="margin-bottom: 16px; text-align: right;">
  <button class="print-btn" onclick="window.print()">Print / Save as PDF</button>
</div>

<div class="header">
  <div>
    <div style="font-size: 18px; font-weight: 800; color: #0369a1; letter-spacing: -0.5px;">BANGALORE WATER SUPPLY AND SEWERAGE BOARD</div>
    <div style="font-size: 13px; font-weight: 600; color: #334155;">Autonomous Monitoring & Leak Isolation Closure Report</div>
    <div style="font-size: 11px; color: #64748b; font-family: monospace;">Ref: {rep['incident_id']} • Corridor: {self.graph_info['corridor_id']}</div>
  </div>
  <div style="text-align: right;">
    <span class="chip chip-crit">CRITICAL RESOLVED</span>
    <span class="chip chip-sim" style="margin-left: 4px;">SIMULATED</span>
  </div>
</div>

<div class="grid">
  <div class="card">
    <span class="label">Incident ID</span>
    <div class="val">{rep['incident_id']}</div>
  </div>
  <div class="card">
    <span class="label">Duration</span>
    <div class="val">{rep.get('duration_min', 1.5)} min</div>
  </div>
  <div class="card">
    <span class="label">Volume Lost</span>
    <div class="val" style="color: #dc2626;">{rep.get('volume_lost_kl', 0.0)} kL</div>
  </div>
  <div class="card">
    <span class="label">Approved By</span>
    <div class="val" style="font-size: 13px;">{rep.get('approved_by', 'AUTO')}</div>
  </div>
</div>

<div class="card" style="margin-bottom: 16px;">
  <div style="font-weight: 700; margin-bottom: 4px;">Incident Synopsis</div>
  <p style="margin: 0; color: #334155;">
    Supply line <strong>{self.graph_info['corridor_id']}</strong> ({self.graph_info['from_station']} to {self.graph_info['to_station']})
    experienced mass-balance deficit accompanied by downstream pressure drop. Monitoring agent automatically isolated the corridor by switching OFF
    <strong>{self.graph_info['feeding_pump_name']}</strong> and closing motorized valve <strong>{self.graph_info['isolation_valve_name']}</strong>.
    Repair was completed, pre-start hydrostatic pressure test passed, and normal supply was restored under soft-start profile.
  </p>
</div>

<div style="font-weight: 700; margin-top: 16px;">Action Timeline & Audit Trail</div>
<table>
  <thead>
    <tr>
      <th style="width: 100px;">Time</th>
      <th style="width: 80px;">Elapsed</th>
      <th>Action / State Transition</th>
    </tr>
  </thead>
  <tbody>
    {timeline_rows}
  </tbody>
</table>

<div class="disclaimer">
  <strong>Operational Governance Notice:</strong> Automatic isolation is simulated. Real field control is not enabled. All pump control and valve transitions executed in the digital twin physics simulation. No direct path to physical RTU or PLC actuators exists.
</div>
</body>
</html>"""

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _set_state(self, state: DemoState):
        self.state = state
        self.state_entered_at = time.time()
        logger.info(f"[LeakDemo] -> {state.value}")

    def _log_step(self, label: str):
        entry = {
            "label": label,
            "ts": time.strftime("%H:%M:%S"),
            "elapsed_s": round(time.time() - (self.demo_started_at or time.time()), 1),
        }
        self.step_log.append(entry)
        try:
            from .monitor import monitoring_agent
            monitoring_agent._log_activity(f"[MonitorAgent] {label}")
        except Exception:
            pass

    def _do_reset(self):
        try:
            sim = _get_sim_engine()
            corridor_id = self.graph_info.get("corridor_id", "CORR_TG_MJ")
            sim.stop_leak(corridor_id)
            if corridor_id != "CORR_TG_MJ":
                sim.stop_leak("CORR_TG_MJ")
            # Restore pump if stopped by demo
            pump_id = self.graph_info["feeding_pump_id"]
            stn = sim.stations_state.get("PS_TATAGUNI", {})
            pdata = stn.get("pumps", {}).get(pump_id)
            if pdata and pdata.get("state") in ("OFF", "STOPPING") and pdata.get("isolated_by_agent"):
                pdata["state"] = "RUNNING"
                fla = pdata["cfg"].get("rated_fla_a", 124.5)
                pdata["current_avg"] = round(fla * 0.87, 1)
                pdata["flow_lps"] = round(pdata["cfg"].get("pump_curve", {}).get("flow_lps_rated", 888.89) * 0.88, 1)
                pdata.pop("isolated_by_agent", None)
                pdata.pop("lock_tag", None)
            self.valve_state = "OPEN"
        except Exception as e:
            logger.warning(f"[LeakDemo] Reset error (non-fatal): {e}")


# Global singleton — used by the router and monitor agent
leak_response_sm = LeakResponseStateMachine()


def generate_report_html(report: Optional[Dict[str, Any]] = None) -> str:
    """Convenience helper to generate print-to-PDF HTML report."""
    if report is not None:
        prev = leak_response_sm.incident_report
        leak_response_sm.incident_report = report
        html = leak_response_sm.generate_report_html()
        leak_response_sm.incident_report = prev
        return html
    return leak_response_sm.generate_report_html()

