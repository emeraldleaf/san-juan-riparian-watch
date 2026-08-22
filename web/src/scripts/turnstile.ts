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
export async function turnstileToken(): Promise<string | undefined> {
  if (!SITEKEY) return undefined; // gate off — no key configured
  try {
    await loadScript();
    const ts = window.turnstile;
    if (!ts) return undefined;
    return await new Promise<string | undefined>((resolve) => {
      const holder = document.createElement('div');
      holder.style.display = 'none';
      document.body.appendChild(holder);
      let id: string | undefined;
      const finish = (token?: string) => {
        clearTimeout(timer);
        try { if (id) ts.remove(id); } catch { /* already gone */ }
        holder.remove();
        resolve(token);
      };
      const timer = setTimeout(() => finish(undefined), 8000);
      try {
        // An invisible widget auto-executes on render, so we don't call
        // execute() ourselves (doing so logs "already executing").
        id = ts.render(holder, {
          sitekey: SITEKEY,
          size: 'invisible',
          callback: (token: string) => finish(token),
          'error-callback': () => finish(undefined),
          'timeout-callback': () => finish(undefined),
        });
      } catch {
        finish(undefined);
      }
    });
  } catch {
    return undefined;
  }
}
