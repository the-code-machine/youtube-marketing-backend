import isodate
from datetime import datetime
from app.models import *
from app.workers.youtube.email_extractor import extract_emails, extract_socials


def transform_all(channels_raw, videos_raw, about_data):

    payload = {
        "channels": [],
        "videos": [],
        "emails": [],
        "socials": [],
        "lead_context": {}
    }

    now = datetime.utcnow()

    seen_emails = set()
    seen_socials = set()

    # ---------------- CHANNELS ----------------

    for c in channels_raw:

        cid = c["id"]
        snip = c["snippet"]
        stats = c["statistics"]
        branding = c.get("brandingSettings", {}).get("channel", {})

        desc = snip.get("description", "")

        # ---- FROM DESCRIPTION ----
        desc_emails = extract_emails(desc)
        desc_socials = extract_socials(desc)

        # ---- FROM ABOUT SCRAPER ----
        about = about_data.get(cid, {})
        about_email = about.get("email")
        about_links = about.get("links", [])

        # merge emails
        all_emails = set(desc_emails)
        if about_email:
            all_emails.add(about_email)

        # merge socials
        socials = set(desc_socials)

        for link in about_links:
            domain = link.split("//")[1].split(".")[0]
            socials.add((domain, link))

        # primary picks
        primary_email = next(iter(all_emails), None)

        primary_ig = None
        primary_web = None

        for p, u in socials:
            if p == "instagram" and not primary_ig:
                primary_ig = u
            if p in ["website", "linktr", "beacons"] and not primary_web:
                primary_web = u

        payload["channels"].append(
            YoutubeChannel(
                channel_id=cid,
                name=snip.get("title"),
                handle=snip.get("customUrl"),
                description=desc,
                thumbnail_url=snip["thumbnails"]["high"]["url"],
                banner_url=branding.get("bannerImageUrl"),
                country_code=snip.get("country"),
                subscriber_count=int(stats.get("subscriberCount", 0)),
                total_video_count=int(stats.get("videoCount", 0)),
                total_view_count=int(stats.get("viewCount", 0)),
                channel_created_at=snip.get("publishedAt"),
                primary_email=primary_email,
                primary_instagram=primary_ig,
                primary_website=primary_web,
                discovery_source="youtube_worker",
                discovered_at=now,
                has_email=True if primary_email else False,
                has_instagram=True if primary_ig else False,
                contacted=False,
                engagement_score=None,
                lead_score=None,
                is_active=True,
                created_at=now,
                updated_at=now
            )
        )

        # emails table
        for e in all_emails:
            if e not in seen_emails:
                payload["emails"].append(ExtractedEmail(channel_id=cid, email=e))
                seen_emails.add(e)

        # socials table
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

    # ---------------- VIDEOS ----------------

    for v in videos_raw:

        snip = v["snippet"]
        stats = v["statistics"]

        dur = int(isodate.parse_duration(v["contentDetails"]["duration"]).total_seconds())

        payload["videos"].append(
            YoutubeVideo(
                video_id=v["id"],
                channel_id=snip["channelId"],
                title=snip["title"],
                description=snip["description"],
                thumbnail_url=snip["thumbnails"]["high"]["url"],
                published_at=snip["publishedAt"],
                duration_seconds=dur,
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                comment_count=int(stats.get("commentCount", 0)),
                tags=snip.get("tags"),
                links=[],
                language=snip.get("defaultAudioLanguage"),
                fetched_at=now,
                created_at=now
            )
        )

        # lead context (latest video title)
        payload["lead_context"][snip["channelId"]] = snip["title"]

        # emails from video description
        for e in extract_emails(snip["description"]):
            if e not in seen_emails:
                payload["emails"].append(
                    ExtractedEmail(channel_id=snip["channelId"], email=e)
                )
                seen_emails.add(e)

    return payload
