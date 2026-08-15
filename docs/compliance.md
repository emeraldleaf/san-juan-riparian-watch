# Data protection — records of processing & DSAR procedure

**Internal accountability record (GDPR Art. 30 / Art. 5(2)).** Not published on the site; the
public-facing statement is `privacy.html` (`/privacy`). Owner: Joshua Dell
(joshua.dell@outlook.com). Last reviewed: 2026-08-15.

This project is a **personal portfolio**, not a commercial service. It is designed to process the
minimum personal data possible — in most flows, none that identifies a person.

---

## 1. Data map (records of processing)

| # | Activity | Personal data | Purpose | Lawful basis | Retention | Recipients / transfer |
|---|----------|---------------|---------|--------------|-----------|-----------------------|
| 1 | Viewing the site | none | Serve static pages | n/a (no personal data) | n/a | none — fonts self-hosted, no analytics, no cookies |
| 2 | Rate-limiting the agent | IP address | Abuse / DoS prevention | Legitimate interest (Art. 6(1)(f)) | **Transient, in-memory only** (`RATE_LIMIT_STORAGE_URI=memory://`); not written to disk | none |
| 3 | Answering a chat question | The question text; possibly personal data if a user types it | Generate a grounded answer | Legitimate interest (providing the requested feature) | **Not persisted** — `TRACE_PERSIST_ENABLED=false` makes trace storage a no-op; processed in memory only | **LLM provider** (OpenRouter; model selectable — Qwen / Llama / OLMo) — may process **outside the EU**. Answers are PII-scrubbed before return. |
| 4 | Session threading | Random per-load UUID (not linked to identity) | Thread one multi-turn conversation | Legitimate interest | In-memory for the request; not a persistent cookie | none |
| 5 | Map tiles | IP address (visitor's browser → Esri) | Display the satellite basemap | Legitimate interest | controlled by Esri, not by us | **Esri** (browser contacts them directly, as for any embedded map) |
| 6 | Web server / infra | possibly IP in transient logs | Operate & secure the host | Legitimate interest | Caddy has **no access-log directive** (no per-request IP logging); `fail2ban` reads SSH auth logs only | Hosting: **Hetzner** (EU, Helsinki) |

**Not collected / not done:** no accounts, no cookies, no analytics, no advertising, no tracking
pixels, no profiling, no automated decision-making with legal effect, no sale or sharing of data.

## 2. Why there is "essentially nothing to retrieve"
There is **no persistent identifier** tying stored data to a person: no login, no cookie, no stable
device id. Chat content is not written to disk (item 3). IPs are used transiently and not stored
(items 2, 6). Consequently, for any access/erasure request there is, in the ordinary case, **no
record that can be linked to the requester**.

## 3. Data-subject request (DSAR) procedure
1. Requests arrive at **joshua.dell@outlook.com** (the intake in `privacy.html`).
2. Acknowledge within a reasonable time; respond within **one month** (GDPR Art. 12(3)).
3. Establish whether *any* data keyed to the requester exists. Given the design above, the truthful
   answer is normally **"no data that identifies you is held,"** with a short explanation of why
   (no accounts, cookies, or stored chat/IP records).
4. If, exceptionally, an identifiable record exists (e.g. the requester previously emailed), honour
   access / rectification / erasure / objection as applicable, or explain any lawful exemption.
5. Inform the requester of their right to lodge a complaint with a supervisory authority.

## 4. Technical & organisational measures (Art. 32)
- **Transport security:** automatic HTTPS (Let's Encrypt via Caddy); HSTS.
- **Application security:** Content-Security-Policy, prompt-injection & indirect-injection guards,
  **PII scrubber on answers**, per-IP rate limit, provider spend cap.
- **Host hardening:** key-only SSH (passwords disabled), `ufw` + a network firewall scoped to the
  admin IP, `fail2ban`, automatic security updates.
- **Data minimization by design:** trace persistence disabled; no analytics; fonts self-hosted so
  no visitor IP is disclosed to a third-party font CDN.

## 5. Processors / third parties
| Party | Role | Location |
|---|---|---|
| Hetzner Online GmbH | Hosting (compute) | EU (Finland) |
| OpenRouter | LLM inference for the agent (model-agnostic — Qwen / Llama / OLMo) | outside the EU (transfer disclosed in `privacy.html`) |
| Esri | Satellite basemap tiles | contacted directly by the visitor's browser |

## 6. Review
Revisit this record if the data flows change — notably if analytics, accounts, cookies, or trace
persistence are ever enabled, or if the LLM/hosting providers change.
