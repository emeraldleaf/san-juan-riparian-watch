// Cloudflare Turnstile — a per-request "a real browser did this" token for the
// public LLM endpoints (/agent/map, /query, /query/stream). The backend gate
// (security/turnstile.py) verifies the token before spending LLM budget.
//
// Off by default: with no PUBLIC_TURNSTILE_SITEKEY configured, turnstileToken()
// resolves to undefined and callers send no header — matching the backend gate,
// which is a passthrough when its secret is unset. So this is safe to ship
// before the Cloudflare widget exists; wiring it on is a build-env + box-env flip.
//
// Fail-soft on the CLIENT, fail-closed on the SERVER: if the widget can't mint a
// token (blocked, offline, timeout) this returns undefined. When the gate is ON
// the backend then answers 403 — the caller surfaces a friendly "try again".

const SITEKEY = import.meta.env.PUBLIC_TURNSTILE_SITEKEY as string | undefined;
const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: Record<string, unknown>) => string;
      execute: (id: string) => void;
      remove: (id: string) => void;
    };
  }
}

let scriptPromise: Promise<void> | null = null;

/** A mint attempt: the token if one was produced, else why not. */
export type MintResult = { token?: string; reason?: string };

function loadScript(): Promise<void> {
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    if (window.turnstile) return resolve();
    const s = document.createElement('script');
    s.src = SCRIPT_URL;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('turnstile script failed to load'));
    document.head.appendChild(s);
  });
  return scriptPromise;
}

/**
 * Mint a fresh single-use Turnstile token via an invisible widget, or undefined
 * when the gate is off / the widget can't produce one. Each call renders a
 * throwaway widget and removes it, so tokens are never reused across requests.
 */
export async function turnstileToken(): Promise<MintResult> {
  if (!SITEKEY) return {}; // gate off — no key configured
  try {
    await loadScript();
    const ts = window.turnstile;
    if (!ts) return { reason: 'script-blocked' };
    return await new Promise<MintResult>((resolve) => {
      // OFF-SCREEN, not display:none. An invisible Turnstile widget still has to
      // render to execute, and a display:none container is documented as unreliable
      // for that — it fails intermittently, which is exactly the symptom seen on
      // 2026-08-27: the backend healthy, /health green, and the occasional request
      // arriving with no token and being refused 403.
      const holder = document.createElement('div');
      holder.style.position = 'absolute';
      holder.style.left = '-9999px';
      holder.style.top = '0';
      holder.setAttribute('aria-hidden', 'true');
      document.body.appendChild(holder);
      let id: string | undefined;
      const finish = (token?: string, reason?: string) => {
        clearTimeout(timer);
        try { if (id) ts.remove(id); } catch { /* already gone */ }
        holder.remove();
        resolve(token ? { token } : { reason: reason || 'no-token' });
      };
      // 12s, not 8s: Cloudflare can escalate an invisible widget to an interactive
      // challenge, which takes longer than a silent pass.
      const timer = setTimeout(() => finish(undefined, 'timeout'), 12000);
      try {
        // An invisible widget auto-executes on render, so we don't call
        // execute() ourselves (doing so logs "already executing").
        // NO `size: 'invisible'`. Cloudflare documents only normal / flexible /
        // compact for size; invisible is a property of the SITEKEY's widget mode,
        // set in the Cloudflare dashboard, not a render option. Passing an
        // undocumented value is how this silently misbehaved.
        //
        // This makes the sitekey's configured mode load-bearing: it must be
        // Invisible. If it is Managed or Non-Interactive the widget expects to be
        // seen, and rendering it off-screen will never complete.
        id = ts.render(holder, {
          sitekey: SITEKEY,
          callback: (token: string) => finish(token),
          // Cloudflare passes an error CODE here and the old version discarded it,
          // so a failed mint was indistinguishable from every other failed mint.
          // Keep the last one so callers can report WHY rather than guessing.
          'error-callback': (code?: string) => finish(undefined, code || 'error'),
          'timeout-callback': () => finish(undefined, 'challenge-timeout'),
        });
      } catch {
        // ts.render() can throw synchronously (bad sitekey, widget already
        // rendered). Without a reason here the caller gets a 403 it cannot explain,
        // which is the gap this whole file was changed to close.
        finish(undefined, 'render-threw');
      }
    });
  } catch {
    return { reason: 'script-load-failed' };
  }
}
