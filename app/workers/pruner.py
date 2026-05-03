"""
app/workers/pruner.py

Daily cleanup worker — keeps the DB lean automatically.
Runs via cron at 3am as a separate systemd oneshot service.
"""
import os
import sys
import logging
from datetime import datetime, timedelta

os.environ["GLOSSOUR_WORKER_MODE"] = "true"
sys.path.append(os.path.abspath("."))

from app.core.database import SessionLocal
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s"
)
logger = logging.getLogger(__name__)


def run():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        logger.info("=== DB Pruner started ===")

        # 1. Keep only last 100 automation_jobs
        r = db.execute(text("""
            DELETE FROM automation_jobs
            WHERE id NOT IN (
                SELECT id FROM automation_jobs
                ORDER BY created_at DESC
                LIMIT 100
            )
        """))
        logger.info(f"automation_jobs: removed {r.rowcount}")

        # 2. campaign_events older than 60 days
        r = db.execute(text("""
            DELETE FROM campaign_events
            WHERE created_at < :cutoff
        """), {"cutoff": now - timedelta(days=60)})
        logger.info(f"campaign_events: removed {r.rowcount}")

        # 3. Leads with no contact info older than 30 days (truly useless)
        r = db.execute(text("""
            DELETE FROM leads
            WHERE primary_email IS NULL
              AND instagram_username IS NULL
              AND created_at < :cutoff
        """), {"cutoff": now - timedelta(days=30)})
        logger.info(f"leads (no contact): removed {r.rowcount}")

        # 4. Stale 'new' leads older than 90 days — never got outreach
        r = db.execute(text("""
            DELETE FROM leads
            WHERE status = 'new'
              AND created_at < :cutoff
        """), {"cutoff": now - timedelta(days=90)})
        logger.info(f"leads (stale new): removed {r.rowcount}")

        # 5. Reset skipped_today from email_worker dedup guard
        r = db.execute(text("""
            UPDATE campaign_leads
            SET status = 'ready_to_send', error_message = NULL
            WHERE status = 'skipped_today'
        """))
        logger.info(f"campaign_leads: reset {r.rowcount} skipped_today rows")

        db.commit()
        logger.info("=== Pruner complete ===")

    except Exception as e:
        logger.error(f"Pruner error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run()