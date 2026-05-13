"""
app/workers/campaign/email_worker.py

Fixes vs previous version:
  - send() → send_email() — matches actual EmailService method name
  - html_content= → body= — matches actual parameter name
  - Returns (bool, error_str) tuple — handled correctly now
  - Removed pl.message_id (field doesn't exist on CampaignLead)
  - Daily channel dedup guard kept intact
"""

import os
os.environ["GLOSSOUR_WORKER_MODE"] = "true"

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.models.lead import Lead
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def _get_channel_ids_emailed_today(db: Session) -> set:
    """Channels that already received an email today (UTC) — across all campaigns."""
    today = datetime.utcnow().date()
    rows = (
        db.query(Lead.channel_id)
        .join(CampaignLead, Lead.id == CampaignLead.lead_id)
        .filter(
            CampaignLead.status == "sent",
            func.date(CampaignLead.sent_at) == today,
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def run_email_campaigns():
    db = SessionLocal()
    try:
        running_campaigns = (
            db.query(Campaign)
            .filter(Campaign.status == "running", Campaign.platform == "email")
            .all()
        )

        if not running_campaigns:
            logger.info("No running email campaigns found.")
            return

        channels_emailed_today = _get_channel_ids_emailed_today(db)
        logger.info(f"📭 Daily dedup guard: {len(channels_emailed_today)} channels already emailed today.")

        email_svc = EmailService()

        for campaign in running_campaigns:
            # ── Check if campaign is finished ──────────────────────────────
            remaining = (
                db.query(func.count(CampaignLead.id))
                .filter(
                    CampaignLead.campaign_id == campaign.id,
                    CampaignLead.status.notin_(["sent", "failed"]),
                )
                .scalar()
            )

            if remaining == 0:
                logger.info(f"🏁 Campaign {campaign.id} finished — marking completed.")
                campaign.status = "completed"
                db.commit()
                continue

            template = campaign.email_template
            if not template:
                logger.warning(f"Campaign {campaign.id} has no template — skipping.")
                continue

            html_layout = template.body or "<div>{{content}}</div>"

            # ── Get batch of ready leads ───────────────────────────────────
            pending = (
        db.query(CampaignLead)
        .filter(
        CampaignLead.campaign_id == campaign.id,
        CampaignLead.status.in_(["review_ready", "ready_to_send"]),
    )
        .limit(100)   # ← was 20, now 100
    .all()
    )

            for pl in pending:
                lead = pl.lead

                if not lead:
                    pl.status = "failed"
                    pl.error_message = "Lead record not found"
                    db.commit()
                    continue

                # ── Daily channel dedup guard ──────────────────────────────
                if lead.channel_id in channels_emailed_today:
                    logger.info(f"⏭️  Skipping {lead.channel_id} — already emailed today.")
                    pl.status = "skipped_today"
                    pl.error_message = "Channel already emailed today — retrying tomorrow."
                    db.commit()
                    continue

                if not lead.primary_email:
                    pl.status = "failed"
                    pl.error_message = "No email address on lead"
                    db.commit()
                    continue

                body_content = pl.ai_generated_body
                subject = pl.ai_generated_subject or template.subject

                if not body_content:
                    pl.status = "failed"
                    pl.error_message = "No AI generated body — re-queue for generation"
                    db.commit()
                    continue

                # ── Build HTML ─────────────────────────────────────────────
                formatted_body = body_content.replace("\n", "<br/>")
                final_html = html_layout.replace("{{content}}", formatted_body)

                # ── SEND — using correct method name and param ─────────────
                try:
                    success, error = email_svc.send_email(
                        to_email=lead.primary_email,
                        subject=subject,
                        body=final_html,          # ← correct param name
                    )

                    if success:
                        pl.status = "sent"
                        pl.sent_at = datetime.utcnow()
                        db.commit()
                        channels_emailed_today.add(lead.channel_id)
                        logger.info(f"✅ Sent to {lead.primary_email} (channel: {lead.channel_id})")
                    else:
                        pl.status = "failed"
                        pl.error_message = str(error)[:500]
                        db.commit()
                        logger.error(f"❌ Failed to send to {lead.primary_email}: {error}")

                except Exception as e:
                    pl.status = "failed"
                    pl.error_message = str(e)[:500]
                    db.commit()
                    logger.error(f"❌ Exception sending to {lead.primary_email}: {e}")

        # ── Reset skipped_today from previous days ─────────────────────────
        _reset_skipped_leads(db)

    except Exception as e:
        logger.error(f"Email worker crashed: {e}", exc_info=True)
    finally:
        db.close()


def _reset_skipped_leads(db: Session):
    """Reset yesterday's skipped leads so they re-enter the queue today."""
    skipped = db.query(CampaignLead).filter(CampaignLead.status == "skipped_today").all()
    if skipped:
        for pl in skipped:
            pl.status = "ready_to_send"
            pl.error_message = None
        db.commit()
        logger.info(f"🔄 Reset {len(skipped)} skipped_today leads → ready_to_send")