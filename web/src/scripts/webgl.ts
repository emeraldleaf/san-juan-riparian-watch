// Guard MapLibre construction behind a WebGL probe. A disabled or crashed GPU
// process (Chrome "BindToCurrentSequence failed", GL_VENDOR=Disabled, Sandboxed=yes)
// makes `new maplibregl.Map(...)` throw a webglcontextcreationerror — and because our
// map inits run at top level, that uncaught throw also aborts the rest of the page
// script (theme toggle, reveals, KPIs). Probe first; on failure render a note.
let cached: boolean | null = null;

export function webglSupported(): boolean {
  if (cached !== null) return cached; // probed once; several maps per page call this
  try {
    const c = document.createElement('canvas');
    const gl = (c.getContext('webgl') || c.getContext('experimental-webgl')) as WebGLRenderingContext | null;
    cached = !!(window.WebGLRenderingContext && gl);
    gl?.getExtension('WEBGL_lose_context')?.loseContext(); // release the probe context, don't hold a live one
  } catch {
    cached = false;
  }
  return cached;
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
