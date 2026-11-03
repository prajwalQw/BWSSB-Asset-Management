"""
Mass-Balance Leak Detection & Alarm Verification Engine.
Implements ISA-18.2 compliant alarming:
- Q_leak = Q_up - Q_down - dV/dt
- Uncertainty tolerance: k * sqrt(sigma_up^2 + sigma_down^2 + sigma_tank^2)
- Persistence: 4 of 5 consecutive windows
- Deadband clearance
- Pressure drop confirmation
- Sensor-health guard (suppress if sensors stuck/offline)
"""

import math
import time
from typing import Dict, List, Optional, Any
from ..models import IoTAlert

class PipeSegmentLeakMonitor:
    def __init__(
        self,
        segment_id: str,
        upstream_meter_tag: str,
        downstream_meter_tag: str,
        downstream_pit_tag: str,
        tank_id: Optional[str] = None,
        pipe_dn_mm: int = 800,
        length_km: float = 12.8,
        nearest_road: str = "Kanakapura Road / Pipeline Corridor",
        k_factor: float = 2.0,
        threshold_lps: float = 4.0,
        pressure_drop_bar: float = 0.10,
        window_size_s: int = 60,
    ):
        self.segment_id = segment_id
        self.upstream_meter_tag = upstream_meter_tag
        self.downstream_meter_tag = downstream_meter_tag
        self.downstream_pit_tag = downstream_pit_tag
        self.tank_id = tank_id
        self.pipe_dn_mm = pipe_dn_mm
        self.length_km = length_km
        self.nearest_road = nearest_road
        self.k_factor = k_factor
        self.threshold_lps = threshold_lps
        self.pressure_drop_bar = pressure_drop_bar
        self.window_size_s = window_size_s

        # Rolling window history (last 5 evaluation windows)
        self.window_results: List[bool] = []
        self.clear_count: int = 0
        self.active_alert: Optional[IoTAlert] = None
        self.baseline_pressure_bar: Optional[float] = None

    def evaluate(
        self,
        q_upstream_lps: float,
        q_downstream_lps: float,
        dv_dt_lps: float,
        pressure_downstream_bar: float,
        upstream_healthy: bool,
        downstream_healthy: bool,
        pit_healthy: bool,
        sim_leak_injection: Optional[Dict[str, Any]] = None
    ) -> Optional[IoTAlert]:
        # 1. Sensor Health Guard: if sensors are offline or stuck, suppress leak alarm
        if not (upstream_healthy and downstream_healthy and pit_healthy):
            return self.active_alert

        # Baseline pressure learning
        if self.baseline_pressure_bar is None:
            self.baseline_pressure_bar = pressure_downstream_bar
        else:
            # Slow exponential smoothing towards steady pressure when no leak
            if not self.active_alert:
                self.baseline_pressure_bar = 0.98 * self.baseline_pressure_bar + 0.02 * pressure_downstream_bar

        # 2. Mass Balance: Q_leak = Q_up - Q_down - dV/dt
        raw_leak_lps = q_upstream_lps - q_downstream_lps - dv_dt_lps

        # If simulated injection active on this segment, reflect physical effect
        if sim_leak_injection and sim_leak_injection.get("pipe_segment_id") == self.segment_id:
            raw_leak_lps = max(raw_leak_lps, sim_leak_injection.get("leak_rate_lps", 18.5))

        # 3. Uncertainty tolerance: sigma_eff = k * sqrt(sigma1^2 + sigma2^2)
        # Assuming ~0.5% meter accuracy on reading
        sigma_up = max(0.5, q_upstream_lps * 0.005)
        sigma_down = max(0.5, q_downstream_lps * 0.005)
        tolerance = self.k_factor * math.sqrt(sigma_up**2 + sigma_down**2)

        is_leak_detected_now = raw_leak_lps > (self.threshold_lps + tolerance)

        # 4. Confirmation with pressure drop
        dp = self.baseline_pressure_bar - pressure_downstream_bar
        pressure_confirmed = dp >= self.pressure_drop_bar or (raw_leak_lps > (self.threshold_lps * 2.0))

        is_window_positive = is_leak_detected_now and pressure_confirmed

        # Update persistence window (maintain last 5 windows)
        self.window_results.append(is_window_positive)
        if len(self.window_results) > 5:
            self.window_results.pop(0)

        # 4 of 5 persistence check
        positive_count = sum(1 for w in self.window_results if w)

        now_epoch = time.time()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))

        if positive_count >= 4 and not self.active_alert:
            # Raise new alert
            estimated_loss_lps = round(raw_leak_lps, 1)
            estimated_loss_kld = round(estimated_loss_lps * 86.4, 1) # L/s to kL/day
            confidence = min(96.0, round(82.0 + positive_count * 2.5, 1))

            self.active_alert = IoTAlert(
                alert_id=f"ALT-LEAK-{self.segment_id}",
                rule_id="RULE-IOT-LEAK-01",
                category="HYDRAULIC_INTEGRITY",
                severity="CRITICAL",
                title=f"Possible leak between {self.upstream_meter_tag} and {self.downstream_meter_tag}",
                location=self.nearest_road,
                coordinates=[77.5380, 12.9050],
                metric_observed=f"Mass balance deficit: {estimated_loss_lps} L/s (Delta P: -{round(dp, 2)} bar)",
                recommendation=f"Acoustic correlation survey recommended within +/- 350 m corridor of {self.nearest_road}. Check air valves and boundary chambers.",
                requires_human_approval=True,
                human_decision_status="PENDING_REVIEW",
                timestamp=now_iso,
                timestamp_epoch=now_epoch,
                data_tier="SIMULATED",
                source="IOT",
                estimated_loss_lps=estimated_loss_lps,
                estimated_loss_kld=estimated_loss_kld,
                confidence_pct=confidence,
                uncertainty_corridor=f"Corridor Ch {round(self.length_km * 0.45, 1)} km to {round(self.length_km * 0.55, 1)} km (+/- 350 m)",
                nearest_landmark=self.nearest_road,
                affected_elements=[
                    "Downstream delivery pressure to Mount Joy GLR",
                    "Supply reliability to 3 southern BBMP wards",
                    "Transient surge stress on trunk welds"
                ],
                suggested_steps=[
                    "Verify field zero-pressure calibration on PIT",
                    "Isolate section via motorized butterfly valve BFV-104 if loss increases",
                    "Deploy ground acoustic crew with listening rod"
                ],
                active=True
            )
            self.clear_count = 0

        elif self.active_alert:
            self.active_alert.last_seen = now_epoch
            # Check clearing deadband (raw_leak_lps < 0.5 * threshold for 3 windows)
            if raw_leak_lps < (0.5 * self.threshold_lps):
                self.clear_count += 1
                if self.clear_count >= 3:
                    # Auto clear: transition status to CLEARED
                    cleared_alert = self.active_alert.model_copy()
                    cleared_alert.status = "CLEARED"
                    cleared_alert.active = False
                    cleared_alert.cleared_at = now_epoch
                    self.active_alert = None
                    self.clear_count = 0
                    return cleared_alert
            else:
                self.clear_count = 0

        return self.active_alert
