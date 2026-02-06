from app.models.youtube_channel import YoutubeChannel
from app.models.youtube_video import YoutubeVideo

def dedupe_existing(db, results):

    existing_channels = set(x[0] for x in db.query(YoutubeChannel.channel_id))
    existing_videos = set(x[0] for x in db.query(YoutubeVideo.video_id))

    channel_ids = set()
    video_ids = set()

    for r in results:
        if r["video_id"] not in existing_videos:
            video_ids.add(r["video_id"])

        if r["channel_id"] not in existing_channels:
            channel_ids.add(r["channel_id"])

    return list(channel_ids), list(video_ids)
