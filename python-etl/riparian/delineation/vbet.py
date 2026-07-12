"""VBET valley bottoms — the *maximum riparian corridor extent*, straight from the source.

Our HAND (Height Above Nearest Drainage) envelope is a **re-derivation** of this. CO-RIP's authors
built it with the Valley-bottom Extraction Tool (Gilbert et al. 2016), manually edited it along every
stream of Strahler order ≤ 3, and published it. It is the same construct, done by the people whose
paper we are measuring ourselves against.

    Evangelista, P., Young, N., Vorster, A., et al. (2018). *Mapping Native and Non-Native Riparian
    Vegetation in the Colorado River Watershed.* CSU/NREL + USGS + NASA DEVELOP.
    Data: Mountain Scholar, "Valley bottom extraction tool results for Colorado River Basin".
    **Licence: CC BY-SA 4.0** — see docs/data-licenses.md. ShareAlike binds our derived products.

Why it matters more than it sounds:

* It **covers all three tiles, including Turkey Creek (CO)** — where NMRipMap does not reach and our
  labels are weakest. Measured: valley-bottom pixels are 20.9% of the Animas tile, 19.5% of Malpais,
  10.3% of Turkey Creek (narrower, as a headwater reach should be).
* It is a **prior, not a label.** A valley bottom is where riparian vegetation *can* be, not where it
  *is*. Used as an envelope it removes the uplands that both the weak labels and NMRipMap kept
  getting wrong — it does not tell you what is inside.
* It lets us **stop re-deriving** a published artefact and spend the effort on the part that is
  actually ours.

## The raster

``CRB_VBETraster.tif`` — 30 m, ESRI:102008 (Albers), ``uint16``, binary:
``100`` = valley bottom, ``65535`` = nodata. Whole Colorado River Basin.

## Fetching it without downloading 1.3 GB

The published archive is ``VBETfiles.zip`` (1.3 GB) and most of that is a **1.66 GB shapefile** we do
not need. Mountain Scholar serves ``Accept-Ranges: bytes``, so :func:`fetch_raster` reads the zip's
central directory over HTTP and extracts **only the 53.8 MB raster member** — about 12 seconds instead
of a 1.3 GB download. (Dryad blocks this; Mountain Scholar does not.)
"""

from __future__ import annotations

import io
import logging
import urllib.request
import zipfile
from pathlib import Path
from typing import Final

import numpy as np

logger = logging.getLogger(__name__)

VBET_ZIP_URL: Final[str] = (
    "https://api.mountainscholar.org/server/api/core/bitstreams/"
    "d1c33df2-92c4-4f7f-96ac-9af1a79fc51b/content"
)
RASTER_MEMBER: Final[str] = "VBET files/CRB_VBETraster.tif"

VALLEY_BOTTOM: Final[int] = 100
NODATA: Final[int] = 65535
RESOLUTION_M: Final[int] = 30
SOURCE: Final[str] = "vbet"
LICENSE: Final[str] = "CC BY-SA 4.0"

_UA: Final[dict[str, str]] = {"User-Agent": "riparian-research/0.1"}


class _HttpRangeFile(io.RawIOBase):
    """A seekable, read-only file over HTTP Range requests.

    Lets :mod:`zipfile` list and extract a single member from a 1.3 GB remote archive without
    downloading it. Clamping ``seek`` to ``[0, size]`` and returning ``b""`` at EOF is load-bearing:
    without it, ``zipfile``'s end-of-central-directory probe walks past the end and the server
    answers **416 Range Not Satisfiable**, which surfaces as a baffling ``BadZipFile``.
    """

    def __init__(self, url: str, size: int | None = None) -> None:
        """
        Args:
            url: The remote file.
            size: Total length in bytes. If omitted, a HEAD request discovers it. Injectable so the
                class can be exercised without a network — a subclass that skipped ``__init__`` to
                avoid the HEAD would leave the base uninitialised, which CodeQL flags (correctly)
                as a missing superclass call.
        """
        super().__init__()
        self.url = url
        self.pos = 0
        if size is not None:
            self.size = size
            return
        req = urllib.request.Request(url, method="HEAD", headers=_UA)
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — fixed https URL
            self.size = int(resp.headers["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        target = (
            offset if whence == 0
            else self.pos + offset if whence == 1
            else self.size + offset
        )
        self.pos = max(0, min(target, self.size))
        return self.pos

    def read(self, size: int = -1) -> bytes:
        if self.pos >= self.size:
            return b""
        if size < 0 or self.pos + size > self.size:
            size = self.size - self.pos
        if size == 0:
            return b""
        req = urllib.request.Request(
            self.url, headers={**_UA, "Range": f"bytes={self.pos}-{self.pos + size - 1}"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            data = resp.read()
        self.pos += len(data)
        return data

    def readinto(self, buffer) -> int:  # type: ignore[no-untyped-def]
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def fetch_raster(dest: Path, *, url: str = VBET_ZIP_URL) -> Path:
    """Extract ``CRB_VBETraster.tif`` (53.8 MB) from the remote 1.3 GB zip. Idempotent.

    Args:
        dest: Where to write the GeoTIFF.
        url: The Mountain Scholar bitstream (overridable for tests).

    Returns:
        The path written.
    """
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 40_000_000:
        logger.info("VBET raster already present: %s", dest)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("extracting %s from the remote archive (range requests, not a 1.3 GB download)",
                RASTER_MEMBER)
    archive = zipfile.ZipFile(io.BufferedReader(_HttpRangeFile(url)))
    with archive.open(RASTER_MEMBER) as src, dest.open("wb") as out:
        while chunk := src.read(4 << 20):
            out.write(chunk)
    logger.info("VBET raster -> %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    return dest


def to_mask(values: np.ndarray) -> np.ndarray:
    """Binary valley-bottom mask from raw raster values.

    ``100`` is valley bottom; everything else — including the ``65535`` nodata sentinel — is not.
    Anything other than those two values is treated as *not* valley bottom rather than guessed at:
    the raster is binary, and inventing a third meaning is how a label set silently goes wrong.
    """
    return values == VALLEY_BOTTOM


def coverage(values: np.ndarray) -> float:
    """Fraction of a window that is valley bottom (0–1). Useful as a sanity check on a new AOI."""
    if values.size == 0:
        return 0.0
    return float(to_mask(values).sum() / values.size)


def is_prior_not_label() -> str:
    """Say the quiet part in code, because it is the thing most likely to be forgotten.

    A valley bottom is where riparian vegetation **can** be, not where it **is**. Using VBET as a
    positive label would teach the model that every gravel bar and dry wash in the floodplain is
    riparian — the same class of error as the unfiltered NMRipMap fetch, which made ~45% of the
    positive class wrong. Use it as an **envelope**: mask out what cannot be riparian, then let the
    spectral/temporal model decide what is.
    """
    return (
        "VBET is a PRIOR (where riparian CAN be), not a LABEL (where it IS). Use it to mask the "
        "uplands, never as a positive class."
    )
