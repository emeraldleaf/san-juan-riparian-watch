---
description: Scaffold a new React/Leaflet map layer following the fetchJson + GeoJSON + legend pattern
argument-hint: <layer + source endpoint, e.g. "riparian extent from /api/riparian/extent">
disable-model-invocation: true
---

# /add-map-layer

Scaffold a new map layer in the React + Leaflet frontend. See CLAUDE.md "Frontend" +
"Common Patterns".

`$ARGUMENTS` names the layer + its source API endpoint. If empty, ask.

This is a **MapLibre GL** map (`react-map-gl/maplibre`), not Leaflet. Layers are
`<Source>` + `<Layer>`; visibility is toggled via the `layout.visibility` paint prop.

## Steps

1. **Choose the source type.** Large layers → **MVT vector tiles**
   (`<Source type="vector" tiles={[`${API_URL}/api/tiles/.../{z}/{x}/{y}.pbf`]}>` — needs a
   matching `/api/tiles/...pbf` endpoint). Smaller layers → **GeoJSON**
   (`<Source type="geojson" data={fc}>`), lazily fetched with the `fetchJson<T>` helper (it
   sends `X-Session-Id`, logs `X-Correlation-Id`, parses `ApiErrorResponse`; never a raw
   `fetch`). API base from `VITE_API_URL`.
2. **Add the `<Layer>`** (`type="fill"`/`"line"`/`"circle"`) with a `layout.visibility`
   bound to a `showX` toggle state. Color via MapLibre paint expressions — `match` on a
   category or `interpolate` on a continuous prop (e.g. `riparian_probability`).
3. **Interactivity** — add the layer id to `interactiveLayerIds` and handle the click in the
   map's `onClick` to show a `<Popup>`.
4. **Add a `LayerToggle`** (state + control) and a **`LegendItem`** (`shape="box"|"line"`) —
   a layer with no legend entry is incomplete.
5. Basemap/raster overlays use a `RasterTileSource`.

## Guardrails

- **No new npm packages without asking.**
- Keep components small; prefer the existing styling/legend patterns over new ones.
- The `vercel-react-best-practices` skill applies for performance (memoization, avoiding
  re-render storms on the map) — load it if the layer is large or updates frequently.
- Verify the layer renders against the running app before claiming done (see
  `verification-before-completion`).
