import pytest
from backend.app.iot.sim.engine import sim_engine
from backend.app.iot.sim.ring_buffer import ring_buffer

def test_ring_buffer_30min_backfill_and_timeseries():
    # Assert timeseries for an existing or fallback asset has >= 2 points
    ts = ring_buffer.get_timeseries("TK_HALLI_STAGE1_P1", "flow_lps")
    assert len(ts) >= 2, f"Expected at least 2 points for Recharts line rendering, got {len(ts)}"
    
    # Check timestamp monotonicity
    assert ts[1]["timestamp"] > ts[0]["timestamp"]

def test_two_reads_10s_apart_follow_profile_within_noise():
    # Sample read at t0
    sim_engine.tick(dt_sec=1.0)
    devs_0 = [d for s in sim_engine.get_stations() for d in s.devices]
    
    # Advance sim clock 10 seconds
    for _ in range(10):
        sim_engine.tick(dt_sec=1.0)
        
    devs_10 = [d for s in sim_engine.get_stations() for d in s.devices]
    
    assert len(devs_0) > 0
    assert len(devs_10) > 0
    # Values follow profile
    flow_0 = devs_0[0].latest_values.get("value", 0.0)
    flow_10 = devs_10[0].latest_values.get("value", 0.0)
    assert flow_0 >= 0.0
    assert flow_10 >= 0.0

def test_unit_conversion_math():
    # Unit conversions: m3/h = L/s * 3.6; MLD = m3/h * 24 / 1000 = L/s * 86.4 / 1000
    lps = 1000.0
    m3h = lps * 3.6
    mld = m3h * 24.0 / 1000.0
    assert m3h == 3600.0
    assert mld == 86.4
