"""
Supply Plan Simulation Executor & Water Movement Physics.
Computes pipe flow velocity (v = Q / A), water travel delays, active flow paths for TripsLayer,
and automated replanning triggers.
"""

import time
import math
import logging
from typing import Dict, List, Any, Optional

from .config import DEFAULT_PIPES, PipeConduit
from .planner import SupplyPlanner

logger = logging.getLogger("bwssb_iot.scheduler.executor")

class PlanExecutor:
    def __init__(self):
        self.planner = SupplyPlanner()
        self.current_plan: Optional[Dict[str, Any]] = None
        self.last_replan_time = 0.0
        self.replan_cooldown_s = 60.0
        self.action_history: List[str] = [
            "06:00 Initialized Automatic Supply Plan: Off-peak replenishment complete",
            "06:30 Mount Joy GLR at 68% capacity, High Grounds GLR at 74% capacity",
            "07:00 Pumping schedule synced with BESCOM Time-of-Use tariff structure"
        ]
        self.speed_multiplier = 1.0
        self.is_paused = False

    def get_or_create_plan(self, sim_time: float, tank_levels: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        if self.current_plan is None or (sim_time - self.last_replan_time > 900.0): # 15 min simulated
            self.replan(sim_time, tank_levels, reason="Periodic 15-minute lookahead recalculation")
        return self.current_plan

    def replan(self, sim_time: float, tank_levels: Optional[Dict[str, float]] = None, reason: str = "") -> Dict[str, Any]:
        self.current_plan = self.planner.solve(sim_time, tank_levels)
        self.last_replan_time = sim_time
        if reason:
            log_entry = f"Re-planned at sim {int(sim_time)}s: {reason}"
            self.action_history.insert(0, log_entry)
            if len(self.action_history) > 50:
                self.action_history.pop()
        logger.info(f"Supply plan updated: {reason}")
        return self.current_plan

    def check_replan_triggers(
        self,
        sim_time: float,
        has_pump_trip: bool,
        has_low_tank: bool,
        has_active_leak: bool,
        tank_levels: Optional[Dict[str, float]] = None
    ) -> bool:
        if sim_time - self.last_replan_time < self.replan_cooldown_s:
            return False

        if has_pump_trip:
            self.replan(sim_time, tank_levels, "Replan triggered: Pump trip detected")
            return True
        elif has_low_tank:
            self.replan(sim_time, tank_levels, "Replan triggered: Reservoir low level warning (<20%)")
            return True
        elif has_active_leak:
            self.replan(sim_time, tank_levels, "Replan triggered: High-loss pipe leak detected")
            return True

        return False

    def compute_water_movement(self, sim_time: float) -> Dict[str, Any]:
        """
        Computes active flow corridors, flow rates (MLD), fluid velocities (m/s),
        and TripsLayer trajectories for deck.gl rendering.
        """
        plan = self.get_or_create_plan(sim_time)
        minute_of_day = int((sim_time % 86400.0) / 60.0)
        step_idx = min(95, max(0, minute_of_day // 15))

        pump_step = plan.get("pump_schedule", [{}])[step_idx]
        valve_step = plan.get("valve_schedule", [{}])[step_idx]

        active_pumps = pump_step.get("active_pumps", [])
        active_valves = valve_step.get("valves", {})

        # Pumping flow from Tataguni
        tg_pump_flow_mld = pump_step.get("flow_mld", 76.8 if len(active_pumps) > 0 else 0.0)

        active_corridors = []
        trips_data = []
        highlighted_zones = []

        # Corridors
        for pipe in DEFAULT_PIPES:
            flow_mld = 0.0
            is_active = False

            if pipe.id == "CORR_TATAGUNI_MOUNT_JOY":
                flow_mld = round(tg_pump_flow_mld * (22.0 / 57.0), 1)
                is_active = flow_mld > 0.0
            elif pipe.id == "CORR_TATAGUNI_HIGH_GROUNDS":
                flow_mld = round(tg_pump_flow_mld * (35.0 / 57.0), 1)
                is_active = flow_mld > 0.0
            elif pipe.id == "CORR_MOUNT_JOY_BASAVANAGUDI":
                if active_valves.get("ZONE_SOUTH_BASAVANAGUDI"):
                    flow_mld = 28.5
                    is_active = True
                    highlighted_zones.append("ZONE_SOUTH_BASAVANAGUDI")
            elif pipe.id == "CORR_MOUNT_JOY_PADMANABHANAGAR":
                if active_valves.get("ZONE_SOUTH_PADMANABHANAGAR"):
                    flow_mld = 24.2
                    is_active = True
                    highlighted_zones.append("ZONE_SOUTH_PADMANABHANAGAR")
            elif pipe.id == "CORR_HIGH_GROUNDS_CBD":
                if active_valves.get("ZONE_CENTRAL_CBD"):
                    flow_mld = 32.0
                    is_active = True
                    highlighted_zones.append("ZONE_CENTRAL_CBD")
            elif pipe.id == "CORR_HIGH_GROUNDS_WEST":
                if active_valves.get("ZONE_WEST_RAJAJINAGAR"):
                    flow_mld = 26.8
                    is_active = True
                    highlighted_zones.append("ZONE_WEST_RAJAJINAGAR")

            # Hydraulic velocity: v = Q / A (m/s)
            # Q in m3/s = (MLD * 1000) / 86400
            # A = pi * (D_m / 2)^2
            d_m = pipe.pipe_dn_mm / 1000.0
            area = math.pi * ((d_m / 2.0) ** 2)
            q_m3s = (flow_mld * 1000.0) / 86400.0 if flow_mld > 0 else 0.0
            velocity = round(q_m3s / area, 2) if area > 0 else 0.0
            travel_time_s = int((pipe.length_km * 1000.0) / velocity) if velocity > 0 else 0

            active_corridors.append({
                "pipe_id": pipe.id,
                "name": pipe.name,
                "is_active": is_active,
                "flow_mld": flow_mld,
                "velocity_ms": velocity,
                "travel_time_min": round(travel_time_s / 60.0, 1),
                "pipe_dn_mm": pipe.pipe_dn_mm,
                "coordinates": pipe.coordinates
            })

            # TripsLayer trail generation if pipe is carrying water
            if is_active and len(pipe.coordinates) >= 2:
                # Assign monotonic timestamps along line vertices
                coords = pipe.coordinates
                n_pts = len(coords)
                total_duration = max(10, min(120, int(30.0 / max(0.2, velocity))))
                waypoints = []
                for idx, coord in enumerate(coords):
                    t_pt = int((idx / max(1, n_pts - 1)) * total_duration)
                    waypoints.append([coord[0], coord[1], t_pt])

                trips_data.append({
                    "id": pipe.id,
                    "name": pipe.name,
                    "color": [14, 165, 233, 220] if flow_mld > 25.0 else [56, 189, 248, 180],
                    "waypoints": waypoints,
                    "flow_mld": flow_mld,
                    "velocity_ms": velocity,
                    "loop_duration": total_duration
                })

        return {
            "sim_time": sim_time,
            "step_idx": step_idx,
            "clock_str": f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}",
            "speed_multiplier": self.speed_multiplier,
            "is_paused": self.is_paused,
            "corridors": active_corridors,
            "trips": trips_data,
            "highlighted_zones": highlighted_zones,
            "active_pumps_count": len(active_pumps),
            "total_pump_flow_mld": tg_pump_flow_mld,
            "recent_actions": self.action_history[:10]
        }

plan_executor = PlanExecutor()
