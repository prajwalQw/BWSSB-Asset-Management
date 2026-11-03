import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { DemoStepper } from '../DemoStepper';
import { AgentResponseCard } from '../AgentResponseCard';
import { IoTLeakDetectionPopup } from '../IoTLeakDetectionPopup';
import { DemoStatus } from '../services/demoApi';
import { IoTAlertItem } from '../../types';

describe('DemoStepper Component', () => {
  it('renders all five stages and SIMULATED badge', () => {
    const status: DemoStatus = {
      state: 'IDLE',
      elapsed_s: 0,
      valve_state: 'OPEN',
      repair_pct: 0,
      repair_eta_s: 0,
      approval_mode: 'auto',
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(<DemoStepper state={status.state} elapsedS={status.elapsed_s} />);
    expect(html).toContain('Leak');
    expect(html).toContain('Detected');
    expect(html).toContain('Isolated');
    expect(html).toContain('Repair');
    expect(html).toContain('Restored');
    expect(html).toContain('SIMULATED');
  });

  it('marks stages complete as state advances to RESTORED', () => {
    const status: DemoStatus = {
      state: 'RESTORED',
      elapsed_s: 88.5,
      valve_state: 'OPEN',
      repair_pct: 100,
      repair_eta_s: 0,
      approval_mode: 'auto',
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(<DemoStepper state={status.state} elapsedS={status.elapsed_s} />);
    expect(html).toContain('88.5');
    expect(html).toContain('Elapsed');
    expect(html).toContain('RESTORED');
  });
});

describe('AgentResponseCard Component', () => {
  it('renders agent diagnostic steps and proposed actions', () => {
    const status: DemoStatus = {
      state: 'AGENT_DIAGNOSED',
      elapsed_s: 12.0,
      valve_state: 'OPEN',
      repair_pct: 0,
      repair_eta_s: 0,
      approval_mode: 'ask',
      agent_response: {
        incident_id: 'INC-DEMO-0042',
        steps: [
          { label: 'Leak confirmed by pressure drop', done: true },
          { label: 'Proposed action: switch OFF High-Lift Pump 1', done: true },
        ],
      },
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(<AgentResponseCard demoStatus={status} />);
    expect(html).toContain('Autonomous Agent Response');
    expect(html).toContain('Leak confirmed by pressure drop');
    expect(html).toContain('switch OFF High-Lift Pump 1');
  });

  it('renders approval buttons with role selector in ask mode', () => {
    const status: DemoStatus = {
      state: 'AWAITING_APPROVAL',
      elapsed_s: 15.0,
      valve_state: 'OPEN',
      repair_pct: 0,
      repair_eta_s: 0,
      approval_mode: 'ask',
      agent_response: {
        incident_id: 'INC-DEMO-0042',
        steps: [{ label: 'Proposed action: switch OFF pump', done: true }],
      },
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(<AgentResponseCard demoStatus={status} />);
    expect(html).toContain('Approve isolation');
    expect(html).toContain('Reject');
    expect(html).toContain('OPERATOR');
    expect(html).toContain('VIEWER');
  });

  it('renders repair progress and ETA during repair stage', () => {
    const status: DemoStatus = {
      state: 'REPAIR_IN_PROGRESS',
      elapsed_s: 45.0,
      valve_state: 'CLOSED',
      repair_pct: 65.0,
      repair_eta_s: 14.0,
      approval_mode: 'auto',
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(<AgentResponseCard demoStatus={status} />);
    expect(html).toContain('65%');
    expect(html).toContain('ETA:');
    expect(html).toContain('Excavation');
  });

  it('renders download post-mortem report button on incident closure', () => {
    const status: DemoStatus = {
      state: 'RESTORED',
      elapsed_s: 90.0,
      valve_state: 'OPEN',
      repair_pct: 100,
      repair_eta_s: 0,
      approval_mode: 'auto',
      incident_report: {
        incident_id: 'INC-DEMO-0042',
        title: 'Transmission Main Leak Closed',
        duration_min: 1.5,
        volume_lost_kl: 54.0,
        energy_saved_kwh: 32.5,
        approved_by: 'K. Srinivas (Duty AE)',
      },
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(<AgentResponseCard demoStatus={status} />);
    expect(html).toContain('Download Report (HTML/PDF)');
  });
});

describe('IoTLeakDetectionPopup Component', () => {
  it('renders dynamic leak popup details and embedded agent response card', () => {
    const mockAlert: IoTAlertItem = {
      alert_id: 'ALT-LEAK-DEMO-01',
      rule_id: 'RULE-IOT-LEAK-01',
      category: 'HYDRAULIC_INTEGRITY',
      severity: 'CRITICAL',
      title: 'Transmission main deficit detected',
      location: 'Pipeline Road Chainage 6+400',
      coordinates: [77.538, 12.905],
      metric_observed: '45.0 L/s flow delta',
      recommendation: 'Acoustic survey and isolation',
      requires_human_approval: true,
      human_decision_status: 'PENDING_REVIEW',
      timestamp: new Date().toISOString(),
      timestamp_epoch: Date.now() / 1000,
      first_seen: Date.now() / 1000,
      data_tier: 'SIMULATED',
      source: 'IOT',
      estimated_loss_lps: 45.0,
      estimated_loss_kld: 3888.0,
      confidence_pct: 94.0,
      uncertainty_corridor: '±300 m range',
      affected_elements: ['Mount Joy GLR', 'Ward 142'],
      suggested_steps: ['Isolate High-Lift Pump 1'],
      active: true,
    };

    const status: DemoStatus = {
      state: 'AGENT_DIAGNOSED',
      elapsed_s: 8.0,
      valve_state: 'OPEN',
      repair_pct: 0,
      repair_eta_s: 0,
      approval_mode: 'auto',
      agent_response: {
        incident_id: 'INC-DEMO-0042',
        steps: [{ label: 'Isolate supply line', done: true }],
      },
      config: {
        from_station: 'Tataguni Terminal Pumping Station',
        to_station: 'Mount Joy GLR',
        impacted_wards: ['Basavanagudi', 'Chamarajpet'],
      },
      step_log: [],
      data_tier: 'SIMULATED',
    };

    const html = renderToString(
      <IoTLeakDetectionPopup
        alerts={[mockAlert]}
        demoStatus={status}
        onShowOnMap={() => {}}
        onAcknowledge={() => {}}
        onSnooze={() => {}}
      />
    );

    expect(html).toContain('Tataguni Terminal Pumping Station');
    expect(html).toContain('Mount Joy GLR');
    expect(html).toContain('45.0');
    expect(html).toContain('3,888');
    expect(html).toContain('Confidence');
    expect(html).toContain('Chainage 5+800 to 7+000');
    expect(html).toContain('Basavanagudi');
    expect(html).toContain('Show on map');
    expect(html).toContain('Acknowledge');
  });
});
