import * as L from 'leaflet';

declare module 'leaflet' {
  function heatLayer(
    latlngs: Array<[number, number] | [number, number, number]>,
    options?: HeatMapOptions,
  ): HeatLayer;

  interface HeatMapOptions {
    minOpacity?: number;
    maxZoom?: number;
    max?: number;
    radius?: number;
    blur?: number;
    gradient?: Record<number, string>;
  }

  interface HeatLayer extends Layer {
    setLatLngs(latlngs: Array<[number, number] | [number, number, number]>): this;
    addLatLng(latlng: [number, number] | [number, number, number]): this;
    setOptions(options: HeatMapOptions): this;
    redraw(): this;
  }
}
