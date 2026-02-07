from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from .database import Base


class VideoStatus(enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Video(Base):
    __tablename__ = "videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)  # Clerk user ID
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=True)  # S3 key for source video
    source_url = Column(String, nullable=True)  # For YouTube URLs
    status = Column(SQLEnum(VideoStatus), default=VideoStatus.PENDING)
    task_id = Column(String, nullable=True)  # Celery task ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    clips = relationship("Clip", back_populates="video", cascade="all, delete-orphan")


class Clip(Base):
    __tablename__ = "clips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    video_id = Column(UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False)
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=True)  # S3 key for clip file
    shorts_s3_key = Column(String, nullable=True)  # S3 key for 9:16 shorts version
    reason = Column(String, nullable=True)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    # New fields for enhanced clip metadata
    virality_score = Column(Integer, nullable=True)  # 0-100 score
    hook_type = Column(String, nullable=True)  # Category of viral hook
    transcript_json = Column(String, nullable=True)  # JSON string of word-level timestamps for captions
    layout_type = Column(String, nullable=True, default="center_crop")  # center_crop, blurred, smart
    created_at = Column(DateTime, default=datetime.utcnow)
    
    video = relationship("Video", back_populates="clips")


