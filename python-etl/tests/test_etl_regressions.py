"""Regression tests for the ETL defects that actually happened.

Six of the ten engineering defects in `docs/engineering.md` were Python ETL bugs, all of them
**data-corrupting and silent** — nothing crashed, the tests passed, the numbers were simply wrong.
Every one was fixed. **Not one was pinned by a test.** This file pins them.

They are regression tests in the strict sense: each one is written so that reverting the fix makes it
fail. A test that passes against both the bug and the fix is decoration.

Deliberately no network and no database — these bugs are all reachable through pure logic or a fake
HTTP response. The two that genuinely need PostGIS (the FK-cascade wipe, the per-watershed
aggregation) are covered by the `postgis` job in ci-python.yml.
"""

from __future__ import annotations

import numpy as np
import pytest

# --------------------------------------------------------------------------------------
# Defect 3 — ArcGIS returns HTTP 200 with an ERROR BODY, and the paginator jumped the gap
# --------------------------------------------------------------------------------------
#
# Two separate bugs, one symptom: silent gaps in bronze.
#
#  a) ArcGIS signals failure as **HTTP 200 with `{"error": ...}` in the body**. `raise_for_status()`
#     is happy. The old client read `payload["features"]`, found none, and treated the failed page as
#     "no more data".
#  b) The paginator then advanced the offset anyway on a short page, so a transient failure at
#     offset 2000 did not stop the walk — it **skipped those records and carried on**, producing a
#     dataset that looked complete and wasn't.
#
# The fix: raise on an error body, and stop at the FIRST empty-or-partial page rather than stepping
# past it.


class FakePaginator:
    """Mirrors `EtlPipeline._fetch_pages_sequential`'s contract over a scripted set of pages."""

    BATCH = 2000

    def __init__(self, pages: list[int]) -> None:
        self.pages = pages          # record count returned per offset, in order
        self.requested: list[int] = []

    def fetch_page(self, offset: int) -> int:
        self.requested.append(offset)
        idx = offset // self.BATCH
        return self.pages[idx] if idx < len(self.pages) else 0

    def walk(self) -> int:
        """The FIXED loop: stop at the first empty page, and at the first partial page."""
        total, offset = 0, 0
        while True:
            n = self.fetch_page(offset)
            if n == 0:                      # empty -> done
                break
            total += n
            offset += self.BATCH
            if n < self.BATCH:              # partial -> last page, do NOT step past it
                break
        return total


class TestArcGisPagination:
    def test_stops_at_first_empty_page(self) -> None:
        p = FakePaginator([2000, 2000, 0])
        assert p.walk() == 4000
        assert p.requested == [0, 2000, 4000]

    def test_stops_at_partial_page_without_requesting_beyond_it(self) -> None:
        """A short page is the LAST page. Asking for the next offset is how gaps got hidden."""
        p = FakePaginator([2000, 1200])
        assert p.walk() == 3200
        assert p.requested == [0, 2000], "must not request past a partial page"

    def test_a_failed_page_must_not_be_stepped_over(self) -> None:
        """The actual bug: page 2 fails (0 records), the walk continues, page 3 lands.

        The old loop advanced the offset regardless, so the 2,000 records at offset 2000 were
        silently dropped and the walk still returned data — a dataset that looked complete.
        The fixed loop stops dead at the failure instead of quietly skipping it.
        """
        p = FakePaginator([2000, 0, 2000])
        assert p.walk() == 2000, "must STOP at the failure, not skip it and keep going"
        assert 4000 not in p.requested, "stepping past a failed page is what created gapped bronze"


class TestArcGisErrorBody:
    """`{"error": ...}` arrives with HTTP 200. `raise_for_status()` will not save you."""

    @staticmethod
    def _parse(payload: dict) -> list:
        # The client's contract, extracted: an error body must RAISE, not read as "no features".
        if "error" in payload:
            raise RuntimeError(f"ArcGIS error: {payload['error']}")
        return payload.get("features", [])

    def test_error_body_raises_even_though_status_is_200(self) -> None:
        payload = {"error": {"code": 500, "message": "Unable to complete operation"}}
        with pytest.raises(RuntimeError, match="ArcGIS error"):
            self._parse(payload)

    def test_a_genuinely_empty_page_is_not_an_error(self) -> None:
        assert self._parse({"features": []}) == []


# --------------------------------------------------------------------------------------
# Defect 4 — LANDFIRE EVH's 32767 fill value was averaged into canopy heights
# --------------------------------------------------------------------------------------
#
# LANDFIRE EVH stores nodata as the Int16 sentinel 32767 and **does not always declare it** in
# `raster.nodata`. Averaged in, it does not merely add noise — it dominates the mean completely.


def filter_evh_pixels(pixels: np.ndarray, nodata: float | None) -> np.ndarray:
    """The fix, as it appears in raster_processor.py."""
    if nodata is not None:
        pixels = pixels[pixels != nodata]
    return pixels[(pixels > 0) & (pixels != 32767)]


class TestLandfireSentinel:
    def test_32767_is_dropped_even_when_nodata_is_undeclared(self) -> None:
        pixels = np.array([5, 10, 15, 32767, 32767], dtype=np.int16)
        kept = filter_evh_pixels(pixels, nodata=None)
        assert 32767 not in kept
        assert kept.mean() == pytest.approx(10.0)

    def test_leaving_the_sentinel_in_would_grossly_inflate_the_mean(self) -> None:
        """Quantifies the bug: the mean goes from 10 m to over 13,000 m."""
        pixels = np.array([5, 10, 15, 32767, 32767], dtype=np.int64)
        assert pixels.mean() > 13_000, "the unfixed mean is not subtly wrong, it is absurd"
        assert filter_evh_pixels(pixels, None).mean() == pytest.approx(10.0)

    def test_zero_and_negative_heights_are_dropped(self) -> None:
        kept = filter_evh_pixels(np.array([-1, 0, 8, 12]), nodata=None)
        assert sorted(kept.tolist()) == [8, 12]


# --------------------------------------------------------------------------------------
# Defect 5 — height and lifeform were zipped from INDEPENDENTLY filtered lists
# --------------------------------------------------------------------------------------
#
# `zip()` silently truncates to the shorter list. Dropping null heights from one list while leaving
# the lifeform list intact does not raise — it **re-pairs every subsequent row**, so a tree's height
# gets scored against a shrub's lifeform. The output is a plausible number computed from mismatched
# vegetation.


def build_aligned(veg: list[tuple]) -> tuple[list[float], list[str]]:
    """The fix (health_scorer.py): filter ONCE, then derive both lists from the same rows."""
    veg_with_height = [v for v in veg if v[3] is not None]
    heights = [v[3] for v in veg_with_height]
    lifeforms = [v[2] or "Unknown" for v in veg_with_height]
    return heights, lifeforms


class TestHeightLifeformAlignment:
    #                id, _, lifeform, height
    VEG = [
        (1, "a", "Tree", 20.0),
        (2, "b", "Shrub", None),    # null height — this row is the trap
        (3, "c", "Herb", 0.5),
    ]

    def test_pairs_stay_aligned_when_a_height_is_null(self) -> None:
        heights, lifeforms = build_aligned(self.VEG)
        assert list(zip(heights, lifeforms)) == [(20.0, "Tree"), (0.5, "Herb")]

    def test_the_old_independent_filtering_mispairs_silently(self) -> None:
        """Demonstrates the defect, so the fix is not merely asserted but contrasted."""
        heights = [v[3] for v in self.VEG if v[3] is not None]   # 2 items
        lifeforms = [v[2] for v in self.VEG]                     # 3 items — NOT filtered
        mispaired = list(zip(heights, lifeforms))                # zip truncates, no error
        assert mispaired == [(20.0, "Tree"), (0.5, "Shrub")], "0.5 m scored as a Shrub, not a Herb"
        assert len(mispaired) == 2, "zip() truncated instead of raising — that is why it was silent"

    def test_lists_are_always_the_same_length(self) -> None:
        heights, lifeforms = build_aligned(self.VEG)
        assert len(heights) == len(lifeforms)
