from sqlalchemy import Column, String, Text, Integer, BigInteger, TIMESTAMP, ARRAY
from app.core.database import Base

class YoutubeVideo(Base):
    __tablename__ = "youtube_videos"

    video_id = Column(String, primary_key=True, index=True)

    channel_id = Column(String)

    title = Column(Text)
    description = Column(Text)
    thumbnail_url = Column(Text)

    published_at = Column(TIMESTAMP)
    duration_seconds = Column(Integer)

    view_count = Column(BigInteger)
    like_count = Column(BigInteger)
    comment_count = Column(BigInteger)

    tags = Column(ARRAY(Text))
    links = Column(ARRAY(Text))

    language = Column(String(10))

    fetched_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)
