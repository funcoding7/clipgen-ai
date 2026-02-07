from fastapi import FastAPI, UploadFile, File, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import os

from .tasks import process_video_task, process_youtube_task, convert_clip_to_shorts_task
from .vector_store import search_video_moments
from .utils import extract_unique_id
from .database import get_db, init_db
from .models import Video, Clip, VideoStatus
from .services.storage import upload_file, get_presigned_url, ensure_bucket_exists

app = FastAPI(title="ClipGen AI API")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Initialize database tables and check S3 bucket on startup"""
    init_db()
    # Try to ensure bucket exists, but don't fail if we can't
    try:
        ensure_bucket_exists()
    except Exception as e:
        print(f"Warning: Could not verify S3 bucket: {e}")
        print("You may need to create the bucket manually in AWS Console")


# Pydantic Schemas
class YoutubeUrlRequest(BaseModel):
    url: str

class ClipResponse(BaseModel):
    id: str
    filename: str
    reason: Optional[str]
    start_time: Optional[float]
    end_time: Optional[float]
    s3_key: Optional[str] = None
    download_url: Optional[str] = None
    shorts_s3_key: Optional[str] = None
    shorts_download_url: Optional[str] = None
    virality_score: Optional[int] = None
    hook_type: Optional[str] = None
    layout_type: Optional[str] = None
    has_transcript: bool = False

    class Config:
        from_attributes = True

class VideoResponse(BaseModel):
    id: str
    filename: str
    source_url: Optional[str]
    status: str
    task_id: Optional[str]
    created_at: str
    s3_key: Optional[str] = None
    clips: List[ClipResponse] = []

    class Config:
        from_attributes = True


def get_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    """Extract user ID from header (set by frontend from Clerk)"""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="User ID required")
    return x_user_id


@app.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    # 1. Generate a unique video ID first
    video_id = uuid.uuid4()
    
    # 2. Save file temporarily
    temp_path = f"uploads/{file.filename}"
    os.makedirs("uploads", exist_ok=True)
    with open(temp_path, "wb+") as file_object:
        file_object.write(file.file.read())
    
    # 3. Upload to S3
    s3_key = f"uploads/{user_id}/{video_id}/{file.filename}"
    upload_success = upload_file(temp_path, s3_key)
    
    if not upload_success:
        raise HTTPException(status_code=500, detail="Failed to upload to S3")
    
    # 4. Create video record in database
    video = Video(
        id=video_id,
        user_id=user_id,
        filename=file.filename,
        s3_key=s3_key,
        status=VideoStatus.PENDING
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    
    # 5. Trigger Celery task (pass s3_key instead of local path)
    task = process_video_task.delay(s3_key, str(video.id), user_id)
    
    # 6. Update video with task_id
    video.task_id = task.id
    video.status = VideoStatus.PROCESSING
    db.commit()
    
    # 7. Cleanup local temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)
    
    return {
        "message": "Processing started",
        "task_id": task.id,
        "video_id": str(video.id)
    }


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    }


@app.post("/process-url")
async def process_youtube_url(
    request: YoutubeUrlRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    video_unique_id = extract_unique_id(request.url)
    video_id = uuid.uuid4()
    
    # Create video record
    video = Video(
        id=video_id,
        user_id=user_id,
        filename=f"youtube_{video_unique_id}",
        source_url=request.url,
        status=VideoStatus.PENDING
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    
    # Trigger task
    task = process_youtube_task.delay(request.url, str(video.id), user_id)
    
    # Update with task_id
    video.task_id = task.id
    video.status = VideoStatus.PROCESSING
    db.commit()
    
    return {
        "message": "Processing started",
        "task_id": task.id,
        "video_id": str(video.id)
    }


@app.get("/videos", response_model=List[VideoResponse])
async def list_user_videos(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """List all videos for the authenticated user"""
    videos = db.query(Video).filter(Video.user_id == user_id).order_by(Video.created_at.desc()).all()
    
    return [
        VideoResponse(
            id=str(v.id),
            filename=v.filename,
            source_url=v.source_url,
            status=v.status.value,
            task_id=v.task_id,
            created_at=v.created_at.isoformat(),
            s3_key=v.s3_key,
            clips=[
                ClipResponse(
                    id=str(c.id),
                    filename=c.filename,
                    reason=c.reason,
                    start_time=c.start_time,
                    end_time=c.end_time,
                    s3_key=c.s3_key,
                    download_url=get_presigned_url(c.s3_key) if c.s3_key else None,
                    virality_score=c.virality_score,
                    hook_type=c.hook_type,
                    layout_type=c.layout_type,
                    has_transcript=c.transcript_json is not None
                ) for c in v.clips
            ]
        )
        for v in videos
    ]


@app.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """Get a specific video with its clips"""
    video = db.query(Video).filter(
        Video.id == uuid.UUID(video_id),
        Video.user_id == user_id
    ).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return VideoResponse(
        id=str(video.id),
        filename=video.filename,
        source_url=video.source_url,
        status=video.status.value,
        task_id=video.task_id,
        created_at=video.created_at.isoformat(),
        s3_key=video.s3_key,
        clips=[
            ClipResponse(
                id=str(c.id),
                filename=c.filename,
                reason=c.reason,
                start_time=c.start_time,
                end_time=c.end_time,
                s3_key=c.s3_key,
                download_url=get_presigned_url(c.s3_key) if c.s3_key else None,
                virality_score=c.virality_score,
                hook_type=c.hook_type,
                layout_type=c.layout_type,
                has_transcript=c.transcript_json is not None
            ) for c in video.clips
        ]
    )


@app.get("/clips/{clip_id}/download")
async def get_clip_download_url(
    clip_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """Get a presigned download URL for a specific clip"""
    clip = db.query(Clip).filter(Clip.id == uuid.UUID(clip_id)).first()
    
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    
    # Verify user owns the video
    video = db.query(Video).filter(Video.id == clip.video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not clip.s3_key:
        raise HTTPException(status_code=404, detail="Clip file not found")
    
    url = get_presigned_url(clip.s3_key)
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
    
    return {"download_url": url, "filename": clip.filename}


class ConvertShortsRequest(BaseModel):
    layout_type: str = "center_crop"  # center_crop, blurred, smart
    enable_captions: bool = False
    caption_style: str = "default"  # default, hormozi, capcut, minimal


@app.post("/clips/{clip_id}/convert-shorts")
async def convert_clip_to_shorts(
    clip_id: str,
    request: ConvertShortsRequest = ConvertShortsRequest(),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """Trigger conversion of a clip to 9:16 shorts format with layout options"""
    clip = db.query(Clip).filter(Clip.id == uuid.UUID(clip_id)).first()
    
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    
    # Verify user owns the video
    video = db.query(Video).filter(Video.id == clip.video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if already converted with same layout
    if clip.shorts_s3_key and clip.layout_type == request.layout_type:
        url = get_presigned_url(clip.shorts_s3_key)
        return {
            "status": "already_converted",
            "shorts_download_url": url,
            "layout_type": clip.layout_type,
            "message": "This clip has already been converted with this layout"
        }
    
    # Trigger async conversion task with layout options
    task = convert_clip_to_shorts_task.delay(
        clip_id, 
        user_id, 
        request.layout_type,
        request.enable_captions,
        request.caption_style
    )
    
    return {
        "status": "processing",
        "task_id": task.id,
        "layout_type": request.layout_type,
        "message": "Conversion to shorts format started"
    }


@app.get("/clips/{clip_id}/shorts")
async def get_clip_shorts_url(
    clip_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """Get the shorts version download URL for a clip"""
    clip = db.query(Clip).filter(Clip.id == uuid.UUID(clip_id)).first()
    
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    
    # Verify user owns the video
    video = db.query(Video).filter(Video.id == clip.video_id, Video.user_id == user_id).first()
    if not video:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not clip.shorts_s3_key:
        return {"status": "not_converted", "shorts_download_url": None}
    
    url = get_presigned_url(clip.shorts_s3_key)
    return {
        "status": "ready",
        "shorts_download_url": url,
        "filename": f"shorts_{clip.filename}"
    }


@app.get("/search/{video_id}")
async def search_video(video_id: str, q: str):
    relevant_moments = search_video_moments(q, video_id)
    return {"query": q, "relevant_segments": relevant_moments}