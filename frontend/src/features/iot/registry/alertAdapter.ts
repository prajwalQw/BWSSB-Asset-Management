import { AlertItem } from '../../../types';
import { IoTAlertItem } from '../types';

/**
 * Adapter that maps IoTAlertItem into the existing AlertItem schema.
 * Leaves all existing AlertItem fields intact and populates optional source: 'IOT'.
 */
export function adaptIoTAlertToTwinAlert(iotAlert: IoTAlertItem): AlertItem {
  return {
    alert_id: iotAlert.alert_id,
    rule_id: iotAlert.rule_id,
    category: iotAlert.category,
    severity: iotAlert.severity,
    title: iotAlert.title,
    location: iotAlert.location,
    coordinates: iotAlert.coordinates,
    metric_observed: iotAlert.metric_observed,
    recommendation: iotAlert.recommendation,
    requires_human_approval: iotAlert.requires_human_approval,
    human_decision_status: iotAlert.human_decision_status,
    timestamp: iotAlert.timestamp,
    data_tier: 'SIMULATED',
    source: 'IOT',
  };
}

export function mergeIoTAlertsWithTwinAlerts(
  existingAlerts: AlertItem[],
  iotAlerts: IoTAlertItem[]
): AlertItem[] {
  const adaptedIoTAlerts = iotAlerts.filter((a) => a.active).map(adaptIoTAlertToTwinAlert);
  // Deduplicate by alert_id
  const seen = new Set<string>();
  const combined: AlertItem[] = [];

  for (const a of adaptedIoTAlerts) {
    seen.add(a.alert_id);
    combined.push(a);
  }

  for (const a of existingAlerts) {
    if (!seen.has(a.alert_id)) {
      seen.add(a.alert_id);
      combined.push(a);
    }
  }

  return combined;
}
