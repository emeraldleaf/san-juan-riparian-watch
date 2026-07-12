"""Run the health scorer standalone against existing silver data."""
import logging
import os

from sqlalchemy import create_engine

from health_scorer import HealthScorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

url = os.environ.get("DATABASE_URL")
if not url:
    raise SystemExit("DATABASE_URL not set")

engine = create_engine(url)
scorer = HealthScorer(engine)
n = scorer.score_all_buffers()
scorer.update_summary()
print(f"Scored {n} buffers")
