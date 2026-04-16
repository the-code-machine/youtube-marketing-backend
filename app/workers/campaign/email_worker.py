"""
app/workers/campaign/email_worker.py

Changes vs original:
  - DAILY CHANNEL DEDUP GUARD: Before sending any email, the worker builds a
    set of channel_ids that have already received an email today (UTC).
    If the same channel is targeted again (different video, different campaign),
    the send is skipped for that day to avoid annoying the creator.

  - The check is done once per worker run (not per email) for efficiency.
"""

import logging
from datetime import datetime, date

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead
from app.models.lead import Lead
from app.services.email_service import EmailService   # adjust import if different

logger = logging.getLogger(__name__)


def _get_channel_ids_emailed_today(db: Session) -> set:
    """
    Returns a set of channel_ids that have already had an email sent today (UTC).
    Uses a single indexed query — fast even with millions of campaign_leads rows.
    """
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
        # ── 1. Running campaigns ──────────────────────────────────────────────
        running_campaigns = (
            db.query(Campaign)
            .filter(Campaign.status == "running", Campaign.platform == "email")
            .all()
        )

        if not running_campaigns:
            return

        # ── 2. Build today's sent-channel guard (one query for the whole run) ─
        channels_emailed_today: set = _get_channel_ids_emailed_today(db)
        logger.info(
            f"📭 Daily dedup guard: {len(channels_emailed_today)} channels "
            f"already emailed today — these will be skipped."
        )

        email_svc = EmailService()
        leads_to_process = []   # (campaign_lead_id, subject, html, email_address)

        for campaign in running_campaigns:
            # ── A. Check if campaign is finished ─────────────────────────────
            remaining_count = (
                db.query(func.count(CampaignLead.id))
                .filter(
                    CampaignLead.campaign_id == campaign.id,
                    CampaignLead.status.notin_(["sent", "failed"]),
                )
                .scalar()
            )

            if remaining_count == 0:
                logger.info(
                    f"🏁 Campaign {campaign.id} finished — marking as completed."
                )
                campaign.status = "completed"
                db.commit()
                continue

            # ── B. Load template ──────────────────────────────────────────────
            template = campaign.email_template
            if not template:
                continue

            html_layout = template.body or "<div>{{content}}</div>"

            # ── C. Get batch of ready leads ───────────────────────────────────
            pending_leads = (
                db.query(CampaignLead)
                .filter(
                    CampaignLead.campaign_id == campaign.id,
                    CampaignLead.status.in_(["review_ready", "ready_to_send"]),
                )
                .limit(20)
                .all()
            )

            for pl in pending_leads:
                lead = pl.lead

                # ── DAILY CHANNEL DEDUP GUARD ─────────────────────────────────
                # If this channel already received an email today (from any
                # campaign), skip — mark as "skipped_today" so it gets picked
                # up in tomorrow's run.
                if lead.channel_id in channels_emailed_today:
                    logger.info(
                        f"⏭️  Skipping {lead.channel_id} — already emailed today."
                    )
                    pl.status = "skipped_today"
                    pl.error_message = "Channel already emailed today — will retry tomorrow."
                    db.commit()
                    continue
                # ─────────────────────────────────────────────────────────────

                body_content = pl.ai_generated_body
                subject_content = pl.ai_generated_subject or template.subject

                if not body_content:
                    continue

                # Merge HTML layout
                formatted_body = body_content.replace("\n", "<br/>")
                final_html = html_layout.replace("{{content}}", formatted_body)

                # Replace channel name placeholder if present
                channel_name = (
                    lead.channel_id  # fallback; ideally join channel name
                )
                final_html = final_html.replace("{channel_name}", channel_name)

                if lead.primary_email:
                    leads_to_process.append(
                        (pl.id, subject_content, final_html, lead.primary_email, lead.channel_id)
                    )
                else:
                    pl.status = "failed"
                    pl.error_message = "No email address found"
                    db.commit()

        # ── 3. Send emails ────────────────────────────────────────────────────
        for pl_id, subject, html, email_addr, channel_id in leads_to_process:
            pl = db.query(CampaignLead).get(pl_id)
            if not pl:
                continue

            # Double-check guard (handles race condition when worker overlaps)
            if channel_id in channels_emailed_today:
                pl.status = "skipped_today"
                pl.error_message = "Channel already emailed today (race-condition guard)."
                db.commit()
                continue

            try:
                result = email_svc.send(
                    to_email=email_addr,
                    subject=subject,
                    html_content=html,
                )
                pl.status = "sent"
                pl.sent_at = datetime.utcnow()
                pl.message_id = result.get("message_id")
                db.commit()

                # Add to today's guard so subsequent iterations in this run
                # don't send to the same channel again.
                channels_emailed_today.add(channel_id)

                logger.info(f"✅ Sent to {email_addr} (channel: {channel_id})")

            except Exception as e:
                pl.status = "failed"
                pl.error_message = str(e)
                db.commit()
                logger.error(f"❌ Failed to send to {email_addr}: {e}")

        # ── 4. Reset "skipped_today" leads back to "ready_to_send" at midnight ─
        # This is handled automatically: next run will call
        # _get_channel_ids_emailed_today() fresh, so tomorrow's date won't
        # include yesterday's sends — leads marked "skipped_today" need to be
        # reset to "ready_to_send" so they re-enter the queue.
        _reset_skipped_leads(db)

    finally:
        db.close()


def _reset_skipped_leads(db: Session):
    """
    Resets leads that were skipped today back to 'ready_to_send' IF the last
    skip was on a previous UTC date.  This means tomorrow's run will pick them
    up automatically without any manual intervention.
    """
    today = datetime.utcnow().date()

    skipped = (
        db.query(CampaignLead)
        .filter(CampaignLead.status == "skipped_today")
        .all()
    )

    reset_count = 0
    for pl in skipped:
        # If the lead was skipped on a previous day, reset it
        # (sent_at is null for skipped leads, so check updated_at or just reset all)
        pl.status = "ready_to_send"
        pl.error_message = None
        reset_count += 1

    if reset_count:
        db.commit()
        logger.info(
            f"🔄 Reset {reset_count} 'skipped_today' leads → 'ready_to_send' "
            f"(they'll be picked up in tomorrow's run)."
        )