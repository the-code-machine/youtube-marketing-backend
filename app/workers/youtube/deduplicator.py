from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo

def dedupe_existing(db, results):
    # Only block existing VIDEOS, let CHANNELS pass through for updates
    incoming_video_ids = list(set(r["video_id"] for r in results))
    
    existing_videos = db.query(YoutubeVideo.video_id)\
        .filter(YoutubeVideo.video_id.in_(incoming_video_ids))\
        .all()
    
    existing_video_set = set(x[0] for x in existing_videos)

    # Filter videos only
    new_results = [r for r in results if r["video_id"] not in existing_video_set]
    
    # Return ALL channel IDs so we can update their stats
    return list(set(r["channel_id"] for r in new_results)), list(set(r["video_id"] for r in new_results))