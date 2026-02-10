import os
import random
import time
import re
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from sqlalchemy import func
from app.core.database import SessionLocal
from app.models.campaign import Campaign, CampaignLead, CampaignEvent

# Ensure these are correct
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
USER_DATA_DIR = "./playwright_data"

def instagram_automation():
    db = SessionLocal()
    job = db.query(CampaignLead).filter(CampaignLead.status == 'ready_to_send').first()
    
    if not job:
        print("💤 No jobs found.")
        return

    with sync_playwright() as p:
        print("🚀 Opening Browser...")
        browser = p.chromium.launch_persistent_context(
    user_data_dir=USER_DATA_DIR,
    headless=False,
    slow_mo=300,
    viewport={"width": 1280, "height": 800},
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox"
    ]
)

        
        page = browser.new_page()
        
        try:
            # 1. Check if truly logged in
            print("🌐 Checking Instagram session...")
            page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")

            page.wait_for_timeout(5000)

            # Look for the 'Home' or 'Search' icon to confirm login
            is_logged_in = page.locator("svg[aria-label='Home']").is_visible() or \
                           page.locator("svg[aria-label='Direct']").is_visible()

            if not is_logged_in:
                print("🔑 Not logged in. Navigating to Login Page...")
                page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                
                print(f"✍️ Entering credentials for {IG_USERNAME}...")
                page.locator("input").nth(0).fill(IG_USERNAME)
                page.locator("input").nth(1).fill(IG_PASSWORD)

                page.get_by_role("button", name="Log in").first.click()



                
                # Wait to see if we land on the dashboard
                page.wait_for_timeout(30000)


            else:
                print("✅ Session confirmed. skipping login.")

            # 2. Navigate to Target
            target_user = job.lead.instagram_username
            print(f"👉 Navigating to {target_user}...")
            page.goto(f"https://www.instagram.com/{target_user}/", wait_until="load")
            page.wait_for_timeout(4000)

            # 3. Clear Modals
            for text in ["Not Now", "Save Info", "Cancel"]:
                btn = page.get_by_role("button", name=re.compile(text, re.IGNORECASE)).first
                if btn.is_visible():
                    print(f"🧹 Clearing popup: {text}")
                    btn.click()
                    page.wait_for_timeout(1000)

            # 4. Open Post
            print("📸 Opening latest post...")
            # We target the link specifically inside the article
            first_post = page.locator("article a").first
            first_post.wait_for(state="visible", timeout=10000)
            first_post.click(force=True)
            page.wait_for_timeout(4000)

            # 5. Comment Logic
            print("💬 Searching for comment box...")
            # Use a regex to find 'Add a comment' regardless of trailing dots
            comment_box = page.get_by_placeholder(re.compile(r"Add a comment", re.IGNORECASE))
            
            if comment_box.is_visible():
                comment_box.click()
                comment_text = job.ai_generated_body or "Great work! 🚀"
                page.keyboard.type(comment_text, delay=random.randint(50, 150))
                page.wait_for_timeout(1000)
                page.keyboard.press("Enter")
                
                print(f"✅ Comment posted: {comment_text}")
                job.status = "sent"
                job.sent_at = datetime.now(timezone.utc)
                db.commit()
            else:
                # Fallback: check if comments are disabled
                if page.get_by_text("Comments on this post have been limited").is_visible():
                    raise Exception("Comments are restricted on this post.")
                else:
                    raise Exception("Comment box not found. User might be logged out or blocked.")

        except Exception as e:
            print(f"❌ ERROR: {e}")
            page.screenshot(path="error_debug.png")
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
        finally:
            browser.close()
            db.close()