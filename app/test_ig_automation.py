import sys
import os
from datetime import datetime
from sqlalchemy.orm import Session

# Setup path to import app modules
sys.path.append(os.path.abspath("."))

from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead, OutreachTemplate
from app.models.lead import Lead
from app.workers.campaign.instagram_worker import instagram_automation

def setup_test_data(db: Session):
    print("🛠️ Setting up Test Data...")

    # 1. Create/Find a Test Lead
    # CHANGE THIS to a real account username you want to test on (e.g. 'instagram' or your alt)
    TEST_USERNAME = "marketingmind.in" 
    
    lead = db.query(Lead).filter(Lead.instagram_username == TEST_USERNAME).first()
    if not lead:
        lead = Lead(
            channel_id="test_channel_001",
            instagram_username=TEST_USERNAME,
            status="new",
            # We remove created_at here if Lead model doesn't have it, 
            # or keep it if Lead model has it. Usually Lead has it.
            created_at=datetime.utcnow() 
        )
        db.add(lead)
        db.commit()
        print(f"   - Created Test Lead: {TEST_USERNAME}")

    # 2. Create a Test Template
    template = db.query(OutreachTemplate).filter(OutreachTemplate.name == "IG Test Script").first()
    if not template:
        template = OutreachTemplate(
            name="IG Test Script",
            type="instagram_comment",
            body_template="Great content! 🔥 Keep it up.",
            is_ai_powered=False
        )
        db.add(template)
        db.commit()

    # 3. Create a Test Campaign
    campaign = db.query(Campaign).filter(Campaign.name == "IG Test Campaign").first()
    if not campaign:
        campaign = Campaign(
            name="IG Test Campaign",
            platform="instagram",
            status="running",
            template_id=template.id
        )
        db.add(campaign)
        db.commit()
        print("   - Created Test Campaign")

    # 4. Link Lead to Campaign (The Job)
    # Delete old jobs to restart test
    db.query(CampaignLead).filter(CampaignLead.lead_id == lead.id).delete()
    db.commit() # Commit the delete first
    
    job = CampaignLead(
        campaign_id=campaign.id,
        lead_id=lead.id,
        status="ready_to_send",
        ai_generated_body="Just testing my new SaaS automation! 🚀 ignore this.",
        # REMOVED created_at=... because the model doesn't support it
    )
    db.add(job)
    db.commit()
    print("   - Created 'Ready to Send' Job")

    return job.id
def run_test():
    db = SessionLocal()
    try:
        # 1. Inject Data
        job_id = setup_test_data(db)
        
        print("\n🚀 STARTING WORKER...")
        print("   - Browser should open shortly.")
        print("   - It will Login -> Go to Profile -> Click Post -> Comment.")
        
        # 2. Run the actual worker function
        instagram_automation()
        
        # 3. Verify Result
        db.expire_all()
        job = db.query(CampaignLead).get(job_id)
        print(f"\n📊 FINAL STATUS: {job.status}")
        
        if job.status == 'sent':
            print("✅ TEST PASSED: Comment posted successfully.")
        elif job.status == 'failed':
            print(f"❌ TEST FAILED: {job.error_message}")
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_test()