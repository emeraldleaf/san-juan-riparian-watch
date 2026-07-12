"""VBET valley bottoms — the prior, and the range-reader that fetches it cheaply.

Two things pinned here:

1. **VBET is a PRIOR, not a LABEL.** A valley bottom is where riparian vegetation *can* be, not where
   it *is*. Using it as a positive class would teach the model that every gravel bar and dry wash in
   the floodplain is riparian — the same class of error as the unfiltered NMRipMap fetch, which made
   ~45% of the positive class wrong.
2. **The nodata sentinel must never become a valley bottom.** `65535` is nodata; only `100` is valley
   bottom. Anything else is *not* valley bottom rather than guessed at.
"""

from __future__ import annotations

import io

import numpy as np
import pytest

from riparian.delineation.vbet import (
    LICENSE,
    NODATA,
    RASTER_MEMBER,
    RESOLUTION_M,
    VALLEY_BOTTOM,
    _HttpRangeFile,
    coverage,
    is_prior_not_label,
    to_mask,
)


class TestMask:
    def test_only_100_is_a_valley_bottom(self) -> None:
        a = np.array([VALLEY_BOTTOM, NODATA, 0, 1, 255], dtype=np.uint16)
        assert to_mask(a).tolist() == [True, False, False, False, False]

    def test_the_nodata_sentinel_is_NOT_a_valley_bottom(self) -> None:
        """65535 averaged in as 'presence' would flood the envelope. Same shape of bug as the
        LANDFIRE 32767 sentinel that inflated canopy heights from 10 m to over 13,000 m."""
        assert not to_mask(np.array([NODATA], dtype=np.uint16))[0]

    def test_coverage_fraction(self) -> None:
        a = np.array([VALLEY_BOTTOM] * 2 + [NODATA] * 8, dtype=np.uint16)
        assert coverage(a) == pytest.approx(0.2)

    def test_coverage_of_an_empty_window_is_zero_not_a_crash(self) -> None:
        assert coverage(np.array([], dtype=np.uint16)) == 0.0


class TestItIsAPriorNotALabel:
    def test_the_contract_is_stated_in_code(self) -> None:
        msg = is_prior_not_label()
        assert "PRIOR" in msg and "LABEL" in msg
        assert "never as a positive class" in msg

    def test_constants(self) -> None:
        assert VALLEY_BOTTOM == 100
        assert NODATA == 65535
        assert RESOLUTION_M == 30
        assert LICENSE == "CC BY-SA 4.0"  # ShareAlike binds our derived products
        assert RASTER_MEMBER.endswith("CRB_VBETraster.tif")


class _FakeRange(_HttpRangeFile):
    """Exercises the range logic against an in-memory buffer — no network."""

    def __init__(self, payload: bytes) -> None:  # noqa: D107 - test double
        self.payload = payload
        self.size = len(payload)
        self.pos = 0
        self.url = "memory://"

    def read(self, size: int = -1) -> bytes:
        # Same guards as the real reader; if these are wrong the server answers 416 and zipfile
        # reports a baffling "BadZipFile".
        if self.pos >= self.size:
            return b""
        if size < 0 or self.pos + size > self.size:
            size = self.size - self.pos
        data = self.payload[self.pos : self.pos + size]
        self.pos += len(data)
        return data


class TestHttpRangeReader:
    """The bug that actually happened: seeking past EOF -> HTTP 416 -> 'File is not a zip file'."""

    def test_seek_is_clamped_and_eof_returns_empty(self) -> None:
        f = _FakeRange(b"0123456789")
        assert f.seek(-22, 2) == 0, "a seek before the start must clamp to 0, not go negative"
        assert f.seek(500) == 10, "a seek past the end must clamp to size"
        assert f.read(4) == b"", "reading at EOF must return b'', never request an invalid range"

    def test_seek_from_end_then_read(self) -> None:
        f = _FakeRange(b"0123456789")
        f.seek(-3, 2)
        assert f.read() == b"789"

    def test_readinto(self) -> None:
        f = _FakeRange(b"abcdef")
        buf = bytearray(3)
        assert f.readinto(buf) == 3
        assert bytes(buf) == b"abc"

    def test_it_can_back_a_zipfile(self) -> None:
        """The whole point: list a zip through the range reader without holding it in memory."""
        import zipfile

        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as z:
            z.writestr("VBET files/CRB_VBETraster.tif", b"not-really-a-tiff")
        archive = zipfile.ZipFile(io.BufferedReader(_FakeRange(blob.getvalue())))
        assert RASTER_MEMBER in archive.namelist()
        with archive.open(RASTER_MEMBER) as fh:
            assert fh.read() == b"not-really-a-tiff"
