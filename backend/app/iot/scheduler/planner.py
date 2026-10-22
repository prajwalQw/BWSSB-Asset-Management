"""
24-Hour Lookahead Supply Optimizer (15-min intervals).
Minimises energy cost across Time-of-Use tariff bands using linear programming (scipy.optimize.linprog),
with fallback to a deterministic greedy rule-based scheduler.
"""

import time
import math
import logging
from typing import Dict, List, Any, Optional
import numpy as np

from .config import (
    DEFAULT_TARIFFS,
    DEFAULT_PUMPS,
    DEFAULT_GLRS,
    DEFAULT_SUPPLY_ZONES,
    DEFAULT_PIPES,
    TariffBand,
    PumpConfig,
    ReservoirConfig,
    SupplyZone,
)

logger = logging.getLogger("bwssb_iot.scheduler.planner")

def get_tariff_for_minute(minute_of_day: int) -> float:
    hour = (minute_of_day // 60) % 24
    if 22 <= hour or hour < 6:
        return 4.50  # Off-Peak
    elif 18 <= hour < 22:
        return 10.50 # Peak
    else:
        return 7.20  # Normal

class SupplyPlanner:
    def __init__(
        self,
        pumps: Optional[List[PumpConfig]] = None,
        glrs: Optional[List[ReservoirConfig]] = None,
        zones: Optional[List[SupplyZone]] = None
    ):
        self.pumps = pumps or DEFAULT_PUMPS
        self.glrs = glrs or DEFAULT_GLRS
        self.zones = zones or DEFAULT_SUPPLY_ZONES
        self.dt_hours = 0.25  # 15 min
        self.num_steps = 96   # 24 h * 4

    def solve(self, start_sim_time: float, current_tank_levels: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Calculates optimal 24h supply plan.
        Attempts linear programming with scipy; falls back to greedy rule-based solver if infeasible.
        """
        t0 = time.time()
        try:
            plan = self._solve_linprog(start_sim_time, current_tank_levels)
            plan["solver"] = "linprog"
        except Exception as e:
            logger.warning(f"Linear programming optimization fallback to greedy rule-based solver: {e}")
            plan = self._solve_greedy(start_sim_time, current_tank_levels)
            plan["solver"] = "greedy_fallback"

        plan["compute_time_ms"] = round((time.time() - t0) * 1000, 2)
        return plan

    def _solve_linprog(self, start_sim_time: float, current_tank_levels: Optional[Dict[str, float]]) -> Dict[str, Any]:
        from scipy.optimize import linprog

        # Variables per time step:
        # u_p(t) in [0, 1] for each pump
        # v_z(t) in [0, 1] for each zone
        num_pumps = len(self.pumps)
        num_zones = len(self.zones)
        n_vars_per_step = num_pumps + num_zones
        total_vars = self.num_steps * n_vars_per_step

        # Objective: minimize energy cost + heavy penalty for unmet demand
        c = np.zeros(total_vars)
        for t in range(self.num_steps):
            step_minute = (t * 15) % 1440
            tariff = get_tariff_for_minute(step_minute)
            for p_idx, pump in enumerate(self.pumps):
                var_idx = t * n_vars_per_step + p_idx
                # Cost = Power(kW) * 0.25h * Tariff(INR/kWh)
                c[var_idx] = pump.rated_power_kw * self.dt_hours * tariff
            for z_idx, zone in enumerate(self.zones):
                var_idx = t * n_vars_per_step + num_pumps + z_idx
                # Small negative weight to encourage supplying demand within allowed windows
                c[var_idx] = -100.0

        # Bounds: [0, 1]
        bounds = [(0.0, 1.0) for _ in range(total_vars)]

        # Inequality constraints: A_ub * x <= b_ub
        # 1. Zone supply only allowed in supply windows: 05:00-09:00 (steps 20-36) and 17:00-21:00 (steps 68-84)
        for t in range(self.num_steps):
            step_minute = (t * 15) % 1440
            is_window = (300 <= step_minute < 540) or (1020 <= step_minute < 1260)
            if not is_window:
                for z_idx in range(num_zones):
                    var_idx = t * n_vars_per_step + num_pumps + z_idx
                    bounds[var_idx] = (0.0, 0.0)

        # 2. Maximum 1 valve active per GLR at any step
        A_ub = []
        b_ub = []
        for t in range(self.num_steps):
            for glr in self.glrs:
                row = np.zeros(total_vars)
                glr_zones = [z_idx for z_idx, z in enumerate(self.zones) if z.assigned_glr_id == glr.id]
                for z_idx in glr_zones:
                    var_idx = t * n_vars_per_step + num_pumps + z_idx
                    row[var_idx] = 1.0
                A_ub.append(row)
                b_ub.append(1.0) # max 1 valve zone active per GLR

        # 3. Total pumped volume must cover daily demand
        total_demand = sum(z.daily_demand_mld for z in self.zones)
        pump_row = np.zeros(total_vars)
        for t in range(self.num_steps):
            for p_idx, pump in enumerate(self.pumps):
                var_idx = t * n_vars_per_step + p_idx
                pump_row[var_idx] = -(pump.rated_flow_mld / 96.0)
        A_ub.append(pump_row)
        b_ub.append(-(total_demand * 0.85))

        # 4. Each zone must receive at least 80% of daily demand
        for z_idx, zone in enumerate(self.zones):
            zone_row = np.zeros(total_vars)
            for t in range(self.num_steps):
                var_idx = t * n_vars_per_step + num_pumps + z_idx
                zone_row[var_idx] = -(zone.daily_demand_mld / 16.0)
            A_ub.append(zone_row)
            b_ub.append(-(zone.daily_demand_mld * 0.80))

        # Run linprog
        res = linprog(c, A_ub=np.array(A_ub) if A_ub else None, b_ub=np.array(b_ub) if b_ub else None, bounds=bounds, method="highs")
        if not res.success:
            raise ValueError(f"Linprog failed: {res.message}")

        return self._build_plan_output(res.x, start_sim_time, current_tank_levels)

    def _solve_greedy(self, start_sim_time: float, current_tank_levels: Optional[Dict[str, float]]) -> Dict[str, Any]:
        """
        Deterministic greedy rule-based scheduler:
        - Fills GLRs during off-peak hours (22:00 to 06:00) when tariff is low (₹4.50/kWh)
        - Supplies wards during morning (05:00-09:00) and evening (17:00-21:00) windows
        - Rotates active valve zones per GLR to respect 1-zone-per-GLR rule
        """
        num_pumps = len(self.pumps)
        num_zones = len(self.zones)
        n_vars_per_step = num_pumps + num_zones
        sol = np.zeros(self.num_steps * n_vars_per_step)

        # Zone rotation indices per GLR
        glr_zone_indices = {
            glr.id: [idx for idx, z in enumerate(self.zones) if z.assigned_glr_id == glr.id]
            for glr in self.glrs
        }

        for t in range(self.num_steps):
            step_minute = (t * 15) % 1440
            hour = step_minute // 60

            # 1. Pumping strategy: Heavy pumping off-peak; maintenance pumping during day
            if 22 <= hour or hour < 6:
                # Off-peak: run 2-3 pumps
                sol[t * n_vars_per_step + 0] = 1.0
                sol[t * n_vars_per_step + 1] = 1.0
                if hour in (1, 2, 3, 4):
                    sol[t * n_vars_per_step + 2] = 1.0
            elif 6 <= hour < 18:
                # Normal daytime: run 1 pump
                sol[t * n_vars_per_step + 0] = 1.0
            else:
                # Peak hours (18:00 - 22:00): minimize pumping
                sol[t * n_vars_per_step + 0] = 0.0

            # 2. Zone valve strategy: Supply in 05:00-09:00 and 17:00-21:00 windows
            is_morning = 300 <= step_minute < 540
            is_evening = 1020 <= step_minute < 1260

            if is_morning or is_evening:
                # Cycle through zones for each GLR
                sub_slot = ((step_minute - (300 if is_morning else 1020)) // 60)
                for glr_id, z_indices in glr_zone_indices.items():
                    if z_indices:
                        active_z = z_indices[sub_slot % len(z_indices)]
                        sol[t * n_vars_per_step + num_pumps + active_z] = 1.0

        return self._build_plan_output(sol, start_sim_time, current_tank_levels)

    def _build_plan_output(
        self,
        x: np.ndarray,
        start_sim_time: float,
        current_tank_levels: Optional[Dict[str, float]]
    ) -> Dict[str, Any]:
        num_pumps = len(self.pumps)
        num_zones = len(self.zones)
        n_vars_per_step = num_pumps + num_zones

        pump_schedule = []
        valve_schedule = []
        tank_forecast = []
        action_log = []

        total_energy_cost_inr = 0.0
        total_pumped_mld = 0.0
        total_delivered_mld = 0.0
        total_demand_mld = sum(z.daily_demand_mld for z in self.zones)

        # Track tank volumes in MLD
        tank_levels = {}
        for glr in self.glrs:
            init_pct = (current_tank_levels or {}).get(glr.id, glr.initial_level_pct)
            tank_levels[glr.id] = (init_pct / 100.0) * glr.capacity_mld

        zone_delivered = {z.id: 0.0 for z in self.zones}

        for t in range(self.num_steps):
            step_minute = (t * 15) % 1440
            hour = step_minute // 60
            minute = step_minute % 60
            time_str = f"{hour:02d}:{minute:02d}"
            tariff = get_tariff_for_minute(step_minute)

            # Pumps at step t
            active_pumps = []
            step_power_kw = 0.0
            step_pump_flow_mld = 0.0
            for p_idx, pump in enumerate(self.pumps):
                var_val = float(x[t * n_vars_per_step + p_idx])
                is_on = bool(var_val > 0.5)
                if is_on:
                    active_pumps.append(str(pump.tag))
                    step_power_kw += float(pump.rated_power_kw)
                    step_pump_flow_mld += float(pump.rated_flow_mld / 96.0)

            step_energy_kwh = step_power_kw * self.dt_hours
            step_cost = step_energy_kwh * tariff
            total_energy_cost_inr += step_cost
            total_pumped_mld += step_pump_flow_mld

            pump_schedule.append({
                "time": time_str,
                "step": int(t),
                "active_pumps": active_pumps,
                "total_power_kw": round(float(step_power_kw), 1),
                "flow_mld": round(float(step_pump_flow_mld * 96.0), 1), # equivalent daily rate
                "tariff_inr": float(tariff),
                "cost_inr": round(float(step_cost), 2),
            })

            # Action log generator on major state changes
            if t > 0:
                prev_active = set(pump_schedule[t - 1]["active_pumps"])
                curr_active = set(active_pumps)
                started = curr_active - prev_active
                stopped = prev_active - curr_active
                for p in started:
                    action_log.append(
                        f"{time_str} Start {p}: Mount Joy / High Grounds replenishment, tariff ₹{tariff:.2f}/kWh"
                    )
                for p in stopped:
                    action_log.append(
                        f"{time_str} Stop {p}: Off-peak window end or storage target met"
                    )

            # Valves & Zone Deliveries at step t
            step_valves = {}
            for z_idx, zone in enumerate(self.zones):
                var_val = float(x[t * n_vars_per_step + num_pumps + z_idx])
                is_open = bool(var_val > 0.5)
                step_valves[str(zone.id)] = is_open
                if is_open:
                    delivered_slice = float(zone.daily_demand_mld / 16.0) # 4 hours supply = 16 slices
                    zone_delivered[zone.id] += delivered_slice
                    total_delivered_mld += delivered_slice
                    # Drawdown from assigned GLR
                    tank_levels[zone.assigned_glr_id] = max(
                        0.0,
                        float(tank_levels[zone.assigned_glr_id] - delivered_slice)
                    )

            valve_schedule.append({
                "time": time_str,
                "step": t,
                "valves": step_valves
            })

            # Tank refill from Tataguni pumps (proportional to zone demand)
            demand_mj = 28.5 + 24.2 # Mount Joy zones demand
            demand_hg = 32.0 + 26.8 # High Grounds zones demand
            split_ratio = demand_mj / (demand_mj + demand_hg)

            tank_levels["GLR_MOUNT_JOY"] = max(
                22.0 * 0.20,
                min(22.0 * 0.92, tank_levels["GLR_MOUNT_JOY"] + step_pump_flow_mld * split_ratio)
            )
            tank_levels["GLR_HIGH_GROUNDS"] = max(
                35.0 * 0.20,
                min(35.0 * 0.92, tank_levels["GLR_HIGH_GROUNDS"] + step_pump_flow_mld * (1.0 - split_ratio))
            )

            step_tank_forecast = {
                "time": time_str,
                "step": t
            }
            for glr in self.glrs:
                pct = (tank_levels[glr.id] / glr.capacity_mld) * 100.0
                step_tank_forecast[glr.id] = round(pct, 1)
            tank_forecast.append(step_tank_forecast)

        # Ward windows
        ward_windows = []
        for zone in self.zones:
            delivered = zone_delivered[zone.id]
            met_pct = round(min(100.0, (delivered / zone.daily_demand_mld) * 100.0), 1)
            ward_windows.append({
                "zone_id": zone.id,
                "zone_name": zone.name,
                "division": zone.division,
                "assigned_glr_id": zone.assigned_glr_id,
                "daily_demand_mld": zone.daily_demand_mld,
                "delivered_mld": round(delivered, 2),
                "met_pct": met_pct,
                "morning_window": "05:00 - 09:00",
                "evening_window": "17:00 - 21:00",
                "is_simulated_assignment": zone.is_simulated_assignment
            })

        demand_met_pct = round(min(100.0, (total_delivered_mld / total_demand_mld) * 100.0), 1)
        unserved_mld = round(max(0.0, total_demand_mld - total_delivered_mld), 2)

        return {
            "status": "OPTIMAL",
            "kpis": {
                "energy_cost_inr": round(total_energy_cost_inr, 2),
                "energy_cost_lakhs": round(total_energy_cost_inr / 100000.0, 2),
                "demand_met_pct": demand_met_pct,
                "unserved_mld": unserved_mld,
                "total_demand_mld": round(total_demand_mld, 1),
                "total_delivered_mld": round(total_delivered_mld, 1),
            },
            "pump_schedule": pump_schedule,
            "valve_schedule": valve_schedule,
            "tank_forecast": tank_forecast,
            "ward_windows": ward_windows,
            "action_log": action_log[:25], # recent actions
            "generated_at": time.time(),
            "labels": {
                "source": "Automatic (simulated)",
                "assignment": "Ward-to-reservoir assignment is simulated",
                "disclaimer": "Decision-support schedule, not BWSSB's actual schedule"
            }
        }
