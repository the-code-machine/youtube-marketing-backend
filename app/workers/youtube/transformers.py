import isodate
from datetime import datetime
from app.models import *
from app.models.channel_metrics import ChannelMetrics
from app.workers.youtube.email_extractor import extract_emails, extract_socials

# ---------------------------------------------------------
# HELPER: Safe Thumbnail Extraction
# ---------------------------------------------------------
def get_thumb(thumbnails):
    """Safely extracts the best available thumbnail url."""
    if not thumbnails:
        return None
    for size in ["high", "medium", "default"]:
        if size in thumbnails:
            return thumbnails[size]["url"]
    return None


def transform_all(channels_raw, videos_raw, about_data,category_id=None):

    # Initialize payload with the new "metrics" list
    payload = {
        "channels": [],
        "videos": [],
        "emails": [],
        "socials": [],
        "metrics": [], 
        "lead_context": {}
    }

    now = datetime.utcnow()

    seen_emails = set()
    seen_socials = set()

    # ---------------------------------------------------------
    # 1. PROCESS CHANNELS
    # ---------------------------------------------------------
    for c in channels_raw:
        try:
            cid = c["id"]
            snip = c["snippet"]
            stats = c["statistics"]
            
            # Extract nested dictionaries safely
            branding = c.get("brandingSettings", {}).get("channel", {})
            topic_details = c.get("topicDetails", {})
            status = c.get("status", {})

            desc = snip.get("description", "")

            # ---- SEO DATA (New) ----
            # Keywords often come as a space-separated string or list. We store as string.
            keywords = branding.get("keywords", "")
            
            # Wikipedia topic URLs (e.g. "Music", "Gaming")
            topic_ids = ",".join(topic_details.get("topicCategories", []))
            
            # B2B Filter: "Made for Kids" usually means low value for B2B leads
            made_for_kids = status.get("madeForKids", False)

            # ---- EMAIL & SOCIAL EXTRACTION ----
            desc_emails = extract_emails(desc)
            desc_socials = extract_socials(desc)

            # From About Page Scraper
            about = about_data.get(cid, {})
            about_email = about.get("email")
            about_links = about.get("links", [])

            # Merge Emails
            all_emails = set(desc_emails)
            if about_email:
                all_emails.add(about_email)

            # Merge Socials
            socials = set(desc_socials)
            for link in about_links:
                # Simple domain extraction for platform ID
                try:
                    domain = link.split("//")[1].split(".")[0]
                    socials.add((domain, link))
                except:
                    continue

            # Identify Primary Contacts
            primary_email = next(iter(all_emails), None)
            primary_ig = None
            primary_web = None

            for p, u in socials:
                if "instagram" in p and not primary_ig:
                    primary_ig = u
                if p in ["website", "linktr", "beacons"] and not primary_web:
                    primary_web = u

            # ---- METRICS CALCULATION (New) ----
            sub_count = int(stats.get("subscriberCount", 0))
            video_count = int(stats.get("videoCount", 0))
            view_count = int(stats.get("viewCount", 0))
            
            # Avoid ZeroDivisionError
            avg_views = (view_count / video_count) if video_count > 0 else 0
            
            # "Engagement Rate" Proxy: Views per Subscriber %
            # (10% is healthy, 1% is dead, 100%+ is viral)
            engagement_rate = (avg_views / sub_count * 100) if sub_count > 0 else 0.0

            # ---- CREATE OBJECTS ----

            # 1. Channel Object
            payload["channels"].append(
                YoutubeChannel(
                    channel_id=cid,
                    name=snip.get("title"),
                    handle=snip.get("customUrl"),
                    description=desc,
                    thumbnail_url=get_thumb(snip.get("thumbnails", {})),
                    banner_url=branding.get("bannerImageUrl"),
                    country_code=snip.get("country"),
                    subscriber_count=sub_count,
                    total_video_count=video_count,
                    total_view_count=view_count,
                    channel_created_at=snip.get("publishedAt"),
                    category_id=category_id,
                    
                    # Contact Info
                    primary_email=primary_email,
                    primary_instagram=primary_ig,
                    primary_website=primary_web,
                    
                    # Discovery Meta
                    discovery_source="youtube_worker",
                    discovered_at=now,
                    
                    # Flags
                    has_email=True if primary_email else False,
                    has_instagram=True if primary_ig else False,
                    contacted=False,
                    
                    # # SEO / Topics (Ensure you added these columns to your Model)
                    # keywords=keywords, 
                    # topic_ids=topic_ids,
                    # made_for_kids=made_for_kids,

                    is_active=True,
                    created_at=now,
                    updated_at=now
                )
            )

            # 2. Channel Metrics Object
            payload["metrics"].append(
                ChannelMetrics(
                    channel_id=cid,
                    avg_views=int(avg_views),
                    avg_likes=0,  # Expensive to calculate, leaving 0 for now
                    avg_comments=0,
                    engagement_rate=round(engagement_rate, 2),
                    subscriber_gain_7d=0,
                    subscriber_gain_30d=0,
                    video_count_7d=0,
                    video_count_30d=0,
                    reply_rate=0.0,
                    ai_lead_score=0.0,
                    updated_at=now
                )
            )

            # 3. Emails Table
            for e in all_emails:
                if e not in seen_emails:
                    payload["emails"].append(ExtractedEmail(channel_id=cid, email=e))
                    seen_emails.add(e)

            # 4. Socials Table
            for p, u in socials:
                key = f"{cid}:{u}"
                if key not in seen_socials:
                    payload["socials"].append(
                        ChannelSocialLink(
                            channel_id=cid,
                            platform=p,
                            url=u
                        )
                    )
                    seen_socials.add(key)

        except Exception as e:
            print(f"Error transforming channel {c.get('id')}: {e}")
            continue

    # ---------------------------------------------------------
    # 2. PROCESS VIDEOS
    # ---------------------------------------------------------
    for v in videos_raw:
        try:
            snip = v["snippet"]
            stats = v["statistics"]
            content = v.get("contentDetails", {})

            # Parse Duration
            try:
                dur = int(isodate.parse_duration(content.get("duration", "PT0S")).total_seconds())
            except:
                dur = 0

            payload["videos"].append(
                YoutubeVideo(
                    video_id=v["id"],
                    channel_id=snip["channelId"],
                    title=snip["title"],
                    description=snip["description"],
                    thumbnail_url=get_thumb(snip.get("thumbnails", {})),
                    published_at=snip["publishedAt"],
                    duration_seconds=dur,
                    
                    # Stats
                    view_count=int(stats.get("viewCount", 0)),
                    like_count=int(stats.get("likeCount", 0)),
                    comment_count=int(stats.get("commentCount", 0)),
                    
                    # Meta
                    tags=snip.get("tags", []),
                    # category_id=snip.get("categoryId"), # New: e.g. "20" (Gaming)
                    # live_broadcast_content=snip.get("liveBroadcastContent", "none"), # New
                    
                    links=[],
                    language=snip.get("defaultAudioLanguage"),
                    fetched_at=now,
                    created_at=now
                )
            )

            # Lead Context (Latest Video Title)
            # This logic overwrites previous titles, ensuring we get the *latest* if the API order allows
            payload["lead_context"][snip["channelId"]] = snip["title"]

            # 5. Extract Emails from Video Description (Secondary Source)
            for e in extract_emails(snip.get("description", "")):
                if e not in seen_emails:
                    payload["emails"].append(
                        ExtractedEmail(channel_id=snip["channelId"], email=e)
                    )
                    seen_emails.add(e)

        except Exception as e:
            print(f"Error transforming video {v.get('id')}: {e}")
            continue

    return payload