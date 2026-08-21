// Guard MapLibre construction behind a WebGL probe. A disabled or crashed GPU
// process (Chrome "BindToCurrentSequence failed", GL_VENDOR=Disabled, Sandboxed=yes)
// makes `new maplibregl.Map(...)` throw a webglcontextcreationerror — and because our
// map inits run at top level, that uncaught throw also aborts the rest of the page
// script (theme toggle, reveals, KPIs). Probe first; on failure render a note.
export function webglSupported(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (c.getContext('webgl') || c.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
}

export function mapFallback(container: HTMLElement): void {
  container.classList.add('map-unavailable');
  container.innerHTML =
    '<div class="map-fallback" role="note">' +
    '<strong>This map needs WebGL</strong>' +
    "<span>Your browser couldn't create a WebGL context. Turn on hardware " +
    'acceleration (in Chrome: Settings → System → “Use graphics acceleration when ' +
    'available”, then relaunch), or open the page in another browser.</span>' +
    '</div>';
}
