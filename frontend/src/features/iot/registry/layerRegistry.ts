/**
 * Layer Registry for Deck.gl Overlay.
 * Allows additive registration of layer providers without modifying core layer generation logic.
 */

export type LayerProvider = (props: any) => any[];

const registry: LayerProvider[] = [];

export const layerRegistry = {
  register(provider: LayerProvider) {
    if (!registry.includes(provider)) {
      registry.push(provider);
    }
  },

  getAllLayers(props: any): any[] {
    const extraLayers: any[] = [];
    for (const provider of registry) {
      try {
        const layers = provider(props);
        if (Array.isArray(layers)) {
          extraLayers.push(...layers);
        }
      } catch (e) {
        console.error('Error executing layer provider in layerRegistry:', e);
      }
    }
    return extraLayers;
  }
};

import { buildIoTDeckLayers } from '../map/iotDeckLayers';

// Auto-register isolated IoT layer provider
layerRegistry.register(buildIoTDeckLayers);
