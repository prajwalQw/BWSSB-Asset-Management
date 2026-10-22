import React from 'react';

/**
 * Additive Section Registry for RightInspector.
 * Allows new inspector sections to be mounted dynamically based on asset predicate.
 */

export interface InspectorSectionProvider {
  predicate: (asset: any) => boolean;
  render: (asset: any, onClose: () => void, onZoomTo?: (coords: [number, number]) => void) => React.ReactNode;
}

const sectionProviders: InspectorSectionProvider[] = [];

export const sectionRegistry = {
  register(provider: InspectorSectionProvider) {
    sectionProviders.push(provider);
  },

  renderSection(asset: any, onClose: () => void, onZoomTo?: (coords: [number, number]) => void): React.ReactNode | null {
    for (const provider of sectionProviders) {
      if (provider.predicate(asset)) {
        return provider.render(asset, onClose, onZoomTo);
      }
    }
    return null;
  }
};
