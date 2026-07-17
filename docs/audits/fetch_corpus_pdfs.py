#!/usr/bin/env python3
"""Fetch open-access PDFs for the riparian methods corpus.

Reads riparian_methods_corpus.csv (the linked version, with an `oa_pdf_url`
column) and downloads each open-access PDF into ./corpus_pdfs/, named by a
filesystem-safe DOI. Stdlib only — runs anywhere with Python 3.

Safe to re-run: already-downloaded files are skipped (resumable). Polite:
one request at a time with a delay. Closed-access papers (no oa_pdf_url) are
listed at the end with their DOI landing page so you can grab them manually.

Set CORPUS_CONTACT_EMAIL before running — publishers want a contact in the user-agent for an
automated fetch, and it is not hardcoded here on purpose: this repo is public, and the next person
should supply their own address rather than inherit (or silently keep sending) someone else's. Same
convention as enrich_corpus.py's OPENALEX_API_KEY.

Usage:
    export CORPUS_CONTACT_EMAIL="you@example.org"
    python3 fetch_corpus_pdfs.py                       # uses ./riparian_methods_corpus.csv
    python3 fetch_corpus_pdfs.py path/to/corpus.csv    # explicit path
"""

import csv
import os
import re
import sys
import time
import urllib.request
import urllib.error

CSV = sys.argv[1] if len(sys.argv) > 1 else "riparian_methods_corpus.csv"
OUT = "corpus_pdfs"
DELAY = 1.0  # seconds between requests (be polite to publishers)
TIMEOUT = 90

CONTACT = os.environ.get("CORPUS_CONTACT_EMAIL")
if not CONTACT:
    # Fail loud, not silently anonymous: an unattributed crawler is what gets an IP blocked.
    sys.exit(
        "CORPUS_CONTACT_EMAIL is not set.\n"
        '  export CORPUS_CONTACT_EMAIL="you@example.org"\n'
        "Publishers expect a contact in the User-Agent for automated fetching."
    )
UA = f"Mozilla/5.0 (research corpus fetch; contact: {CONTACT})"


def safe(doi: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", doi.strip().lower()) or "no_doi"


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(CSV) as f:
        rows = list(csv.DictReader(f))
    have_pdf = [r for r in rows if r.get("oa_pdf_url", "").strip()]
    closed = [r for r in rows if not r.get("oa_pdf_url", "").strip()]
    print(f"{len(rows)} papers | {len(have_pdf)} with OA-PDF | {len(closed)} closed")
    ok = skip = fail = 0
    failures = []
    for i, r in enumerate(have_pdf, 1):
        doi = r.get("doi", "").strip()
        url = r["oa_pdf_url"].strip()
        dest = os.path.join(OUT, safe(doi) + ".pdf")
        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            skip += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            # sanity: PDFs start with %PDF; some OA links redirect to HTML paywalls
            if not data[:5].startswith(b"%PDF"):
                raise ValueError("not a PDF (likely HTML redirect/paywall)")
            with open(dest, "wb") as f:
                f.write(data)
            ok += 1
            print(
                f"[{i}/{len(have_pdf)}] OK  {safe(doi)}.pdf  ({len(data) // 1024} KB)"
            )
        # Catch the retrieval/validation failure modes explicitly — NOT a bare Exception. OSError
        # covers URLError and TimeoutError (both subclass it); ValueError is our own "not a PDF"
        # raise above. Both belong in fetch_failures.csv, listed on purpose, not swallowed blindly.
        except (OSError, ValueError) as e:
            fail += 1
            failures.append((doi, url, str(e)[:80]))
            print(f"[{i}/{len(have_pdf)}] FAIL {doi}: {str(e)[:80]}")
        time.sleep(DELAY)
    print(f"\nDONE  downloaded {ok} | skipped(existing) {skip} | failed {fail}")
    if failures:
        with open("fetch_failures.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["doi", "url", "error"])
            w.writerows(failures)
        print(
            f"  {len(failures)} failures written to fetch_failures.csv (retry or grab manually)"
        )
    if closed:
        with open("closed_access.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["title", "year", "doi_url"])
            for r in closed:
                w.writerow(
                    [r.get("title", ""), r.get("year", ""), r.get("doi_url", "")]
                )
        print(
            f"  {len(closed)} closed-access papers → closed_access.csv (DOI landing pages)"
        )


if __name__ == "__main__":
    main()
