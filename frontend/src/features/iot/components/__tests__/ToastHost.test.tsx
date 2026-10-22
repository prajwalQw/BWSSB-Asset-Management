import { describe, it, expect } from 'vitest';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { ToastHost } from '../ToastHost';
import { IoTAlertItem } from '../../types';

describe('ToastHost Component and Alert Logic', () => {
  it('renders no popups when there are no active alerts', () => {
    const html = renderToString(<ToastHost alerts={[]} />);
    expect(html).not.toContain('Possible leak');
  });

  it('renders high & critical alert popups with loss, confidence, and action buttons', () => {
    const mockAlert: IoTAlertItem = {
      alert_id: 'ALT-LEAK-TEST',
      rule_id: 'RULE-IOT-LEAK-01',
      category: 'HYDRAULIC_INTEGRITY',
      severity: 'CRITICAL',
      title: 'Possible leak between Tataguni Pumping Complex and Mount Joy GLR',
      location: 'Pipeline Corridor V-104',
      coordinates: [77.538, 12.905],
      metric_observed: 'Mass balance deficit: 45.0 L/s',
      recommendation: 'Acoustic survey recommended',
      requires_human_approval: true,
      human_decision_status: 'PENDING_REVIEW',
      timestamp: new Date().toISOString(),
      timestamp_epoch: Date.now() / 1000,
      first_seen: Date.now() / 1000,
      data_tier: 'SIMULATED',
      source: 'IOT',
      estimated_loss_lps: 45.0,
      estimated_loss_kld: 3888.0,
      confidence_pct: 92.5,
      uncertainty_corridor: '±350 m range',
      affected_elements: ['Mount Joy GLR inlet delivery', 'Ward 142 supply'],
      suggested_steps: ['Isolate section via BFV-104'],
      active: true,
    };

    const html = renderToString(
      <ToastHost
        alerts={[mockAlert]}
        onZoomTo={() => {}}
        onAcknowledge={() => {}}
        onSnooze={() => {}}
      />
    );

    // Verify popup content
    expect(html).toContain('Possible leak between Tataguni Pumping Complex and Mount Joy GLR');
    expect(html).toContain('45.0');
    expect(html).toContain('L/s');
    expect(html).toContain('3888');
    expect(html).toContain('kL/day');
    expect(html).toContain('92.5');
    expect(html).toContain('Show on map');
    expect(html).toContain('Acknowledge');
    expect(html).toContain('Snooze');
    expect(html).toContain('Mount Joy GLR inlet delivery');
  });

  it('suppresses lower severities (LOW / MEDIUM) so they only appear in the alerts list', () => {
    const mockLowAlert: IoTAlertItem = {
      alert_id: 'ALT-LOW-TEST',
      rule_id: 'RULE-IOT-INFO-01',
      category: 'OPERATIONAL',
      severity: 'INFO',
      title: 'Routine communication heartbeat',
      active: true,
      requires_human_approval: false,
      human_decision_status: 'INFO_ONLY',
      timestamp: new Date().toISOString(),
      data_tier: 'SIMULATED',
      source: 'IOT',
    };

    const html = renderToString(<ToastHost alerts={[mockLowAlert]} />);
    expect(html).not.toContain('Routine communication heartbeat');
  });
});
