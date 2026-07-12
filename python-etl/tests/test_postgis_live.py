"""Live-PostGIS tests for the two ETL defects that no mock can catch.

Every C# test mocks `IPostGisRepository`, and every Python test until now was a pure function. So the
SQL itself — the FK cascades, the PostGIS operators, the correlated aggregation — **was never executed
anywhere**, in any gate. Two of the six ETL defects lived precisely there:

- **Defect 2** — a full ETL run silently emptied `silver.buffer_wetlands`. `TRUNCATE ... CASCADE` on
  `riparian_buffers` takes every dependent table with it, and `analyze_buffer_wetlands()` had been
  commented out of `run()`, so nothing rebuilt it. The pipeline reported success. The table was empty.
- **Defect 6** — the gold summary aggregated **basin-wide** instead of per watershed, so every
  watershed reported the same number.

Neither is reachable without a real database. A mock returns whatever you told it to.

Marked `live_db`. Skipped locally unless `RIPARIANDB_TEST_URI` is set; **run in CI** against a real
`postgis/postgis` service container (see `.github/workflows/ci-python.yml`).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

DB_URI = os.environ.get("RIPARIANDB_TEST_URI")

pytestmark = [
    pytest.mark.live_db,
    pytest.mark.skipif(not DB_URI, reason="RIPARIANDB_TEST_URI not set — needs a live PostGIS"),
]


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DB_URI, pool_pre_ping=True)
    with eng.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        c.execute(text("DROP SCHEMA IF EXISTS silver CASCADE"))
        c.execute(text("DROP SCHEMA IF EXISTS bronze CASCADE"))
        c.execute(text("CREATE SCHEMA bronze"))
        c.execute(text("CREATE SCHEMA silver"))
        # The shape that matters: a dependent table with an FK onto riparian_buffers.
        c.execute(text("""
            CREATE TABLE bronze.streams (id SERIAL PRIMARY KEY, name TEXT)
        """))
        c.execute(text("""
            CREATE TABLE silver.riparian_buffers (
                id SERIAL PRIMARY KEY,
                stream_id INTEGER NOT NULL REFERENCES bronze.streams(id),
                geom geometry(Geometry, 4269)
            )
        """))
        c.execute(text("""
            CREATE TABLE silver.buffer_wetlands (
                id SERIAL PRIMARY KEY,
                buffer_id INTEGER NOT NULL REFERENCES silver.riparian_buffers(id),
                acres NUMERIC
            )
        """))
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def seed(engine):
    with engine.begin() as c:
        c.execute(text("TRUNCATE silver.buffer_wetlands, silver.riparian_buffers, bronze.streams "
                       "RESTART IDENTITY CASCADE"))
        c.execute(text("INSERT INTO bronze.streams (name) VALUES ('Animas'), ('La Plata')"))
        c.execute(text("""
            INSERT INTO silver.riparian_buffers (stream_id, geom) VALUES
              (1, ST_GeomFromText('POLYGON((-108 37, -108 37.01, -107.99 37.01, -108 37))', 4269)),
              (2, ST_GeomFromText('POLYGON((-107 37, -107 37.01, -106.99 37.01, -107 37))', 4269))
        """))
        c.execute(text("INSERT INTO silver.buffer_wetlands (buffer_id, acres) VALUES (1, 3.5), (2, 1.25)"))


def _count(engine, table: str) -> int:
    with engine.connect() as c:
        return c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


class TestFkCascadeWipesDependents:
    """Defect 2 — the wipe nobody saw, because nothing crashed."""

    def test_truncate_cascade_on_buffers_empties_buffer_wetlands(self, engine) -> None:
        """This is the DEFECT, asserted as real behaviour — not a hypothesis.

        A full ETL run truncates riparian_buffers. CASCADE is not optional here: PostgreSQL refuses
        a plain TRUNCATE while an FK references the table. So the dependent rows go, silently, and
        anything that does not explicitly rebuild them is left with an empty table and a green run.
        """
        assert _count(engine, "silver.buffer_wetlands") == 2

        with engine.begin() as c:
            c.execute(text("TRUNCATE silver.riparian_buffers CASCADE"))

        assert _count(engine, "silver.buffer_wetlands") == 0, (
            "CASCADE took the dependents. If the pipeline does not rebuild them, the table stays "
            "empty and the run still reports success."
        )

    def test_plain_truncate_is_refused_so_cascade_cannot_be_avoided(self, engine) -> None:
        """Rules out the tempting 'just don't use CASCADE' fix — Postgres will not allow it."""
        from sqlalchemy.exc import DatabaseError

        with pytest.raises(DatabaseError, match="(?i)cascade|foreign key"):
            with engine.begin() as c:
                c.execute(text("TRUNCATE silver.riparian_buffers"))

    def test_the_fix_is_to_rebuild_dependents_after_the_wipe(self, engine) -> None:
        """`analyze_buffer_wetlands()` must run in `run()`; it had been commented out.

        NB — the rebuilt buffer does NOT get id 1. `TRUNCATE` (without `RESTART IDENTITY`) leaves the
        SERIAL sequence where it was, so the new row lands on a fresh id. The rebuild must therefore
        reference the id the database actually assigned, not the one it had last run.

        This test was originally written with a hard-coded `buffer_id = 1` and the live database
        rejected it with a ForeignKeyViolation. **A mock would have accepted it happily** — which is
        the entire argument for running the SQL for real.
        """
        with engine.begin() as c:
            c.execute(text("TRUNCATE silver.riparian_buffers CASCADE"))
            new_id = c.execute(text("""
                INSERT INTO silver.riparian_buffers (stream_id, geom) VALUES
                  (1, ST_GeomFromText('POLYGON((-108 37, -108 37.01, -107.99 37.01, -108 37))', 4269))
                RETURNING id
            """)).scalar_one()
            # the rebuild step that had been commented out of run()
            c.execute(
                text("INSERT INTO silver.buffer_wetlands (buffer_id, acres) VALUES (:bid, 3.5)"),
                {"bid": new_id},
            )

        assert new_id != 1, "TRUNCATE does not reset the sequence — do not assume stable ids"
        assert _count(engine, "silver.buffer_wetlands") == 1


class TestPerWatershedAggregation:
    """Defect 6 — the summary was computed basin-wide, so every watershed got the same number."""

    def test_correlated_per_watershed_join_gives_distinct_values(self, engine) -> None:
        with engine.begin() as c:
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS bronze.watersheds (
                    id SERIAL PRIMARY KEY, huc8 TEXT, geom geometry(Geometry, 4269))
            """))
            c.execute(text("TRUNCATE bronze.watersheds RESTART IDENTITY CASCADE"))
            c.execute(text("""
                INSERT INTO bronze.watersheds (huc8, geom) VALUES
                  ('A', ST_GeomFromText('POLYGON((-108.5 36.5, -108.5 37.5, -107.5 37.5, -107.5 36.5, -108.5 36.5))', 4269)),
                  ('B', ST_GeomFromText('POLYGON((-107.5 36.5, -107.5 37.5, -106.5 37.5, -106.5 36.5, -107.5 36.5))', 4269))
            """))

        # basin-wide (the BUG): one number, applied to everyone
        with engine.connect() as c:
            basin_wide = c.execute(text(
                "SELECT COUNT(*) FROM silver.riparian_buffers")).scalar_one()

            # per-watershed (the FIX): bbox pre-filter + ST_Intersects, correlated on watershed id
            rows = c.execute(text("""
                SELECT w.huc8, COUNT(b.id) AS n
                FROM bronze.watersheds w
                LEFT JOIN silver.riparian_buffers b
                  ON b.geom && w.geom AND ST_Intersects(b.geom, w.geom)
                GROUP BY w.huc8 ORDER BY w.huc8
            """)).all()

        per_ws = {r.huc8: r.n for r in rows}
        assert basin_wide == 2
        assert per_ws == {"A": 1, "B": 1}, "each watershed must count only its OWN buffers"
        assert not all(v == basin_wide for v in per_ws.values()), (
            "the bug was assigning the basin-wide total to every watershed"
        )
