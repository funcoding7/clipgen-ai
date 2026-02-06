# app/tasks.py
from celery import Celery
import subprocess
import os
import tempfile
import multiprocessing

# Fix macOS fork() crash - must be before any other imports that might fork
if multiprocessing.get_start_method(allow_none=True) != 'spawn':
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

from .ai_logic import identify_viral_clips
from .utils import create_video_clip
from .vector_store import index_transcript
from .database import SessionLocal
from .models import Video, Clip, VideoStatus
from .services.storage import download_file, upload_file, get_temp_path

# Initialize Celery
celery_app = Celery('worker', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

# Lazy load whisper model to avoid fork issues
_model = None

def get_whisper_model():
    global _model
    if _model is None:
        import whisper
        _model = whisper.load_model("base")
    return _model


def get_db_session():
    """Get a database session for Celery tasks"""
    return SessionLocal()


@celery_app.task(name="process_video")
def process_video_task(s3_key: str, video_id: str, user_id: str):
    """
    Process a video that has been uploaded to S3.
    
    Args:
        s3_key: S3 key of the source video
        video_id: UUID of the video record
        user_id: User ID for organizing clips in S3
    """
    db = get_db_session()
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Extract filename from s3_key
        filename = os.path.basename(s3_key)
        input_path = os.path.join(temp_dir, filename)
        audio_path = os.path.join(temp_dir, f"{os.path.splitext(filename)[0]}.mp3")
        
        # 1. Download source video from S3
        print(f"Downloading from S3: {s3_key}")
        if not download_file(s3_key, input_path):
            raise Exception("Failed to download source video from S3")
        
        # 2. Extract Audio using FFmpeg
        subprocess.run([
            'ffmpeg', '-i', input_path, '-vn',
            '-acodec', 'libmp3lame', '-y', audio_path
        ], check=True)

        # 3. Transcribe with Whisper
        model = get_whisper_model()
        result = model.transcribe(audio_path)

        # 4. Index for search
        try:
            index_transcript(video_id, result["segments"])
        except Exception as e:
            print(f"Error indexing transcript: {e}")

        # 5. Get AI suggestions for viral clips
        ai_suggestions = identify_viral_clips(result["segments"])
        
        # 6. Create clips, upload to S3, save to database
        created_clips = []
        for i, clip in enumerate(ai_suggestions):
            clip_filename = f"{video_id}_clip_{i}.mp4"
            local_clip_path = os.path.join(temp_dir, clip_filename)
            
            # Create the clip locally
            create_video_clip(input_path, local_clip_path, clip['start'], clip['end'])
            
            # Upload clip to S3
            clip_s3_key = f"clips/{user_id}/{video_id}/{clip_filename}"
            upload_success = upload_file(local_clip_path, clip_s3_key)
            
            if not upload_success:
                print(f"Warning: Failed to upload clip {clip_filename} to S3")
                continue
            
            # Save clip to database with S3 key
            db_clip = Clip(
                video_id=video_id,
                filename=clip_filename,
                s3_key=clip_s3_key,
                reason=clip.get('reason', ''),
                start_time=clip['start'],
                end_time=clip['end']
            )
            db.add(db_clip)
            created_clips.append({
                "file": clip_filename,
                "s3_key": clip_s3_key,
                "reason": clip.get('reason', '')
            })
        
        # 7. Update video status to completed
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.COMPLETED
        
        db.commit()

        return {"status": "Complete", "clips": created_clips}
    
    except Exception as e:
        print(f"Error processing video: {e}")
        # Mark video as failed
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
        db.commit()
        raise e
    
    finally:
        db.close()
        # Cleanup temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@celery_app.task(name="process_youtube")
def process_youtube_task(url: str, video_id: str, user_id: str):
    """
    Process a YouTube video by downloading, uploading to S3, then processing.
    
    Args:
        url: YouTube URL
        video_id: UUID of the video record
        user_id: User ID for organizing files in S3
    """
    from .utils import download_youtube_video
    
    db = get_db_session()
    
    # Download YouTube video to local temp
    filename = download_youtube_video(url)
    if not filename:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
        db.commit()
        db.close()
        return {"status": "Failed", "error": "Could not download video"}
    
    # Upload downloaded video to S3
    local_path = f"uploads/{filename}"
    s3_key = f"uploads/{user_id}/{video_id}/{filename}"
    
    upload_success = upload_file(local_path, s3_key)
    if not upload_success:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
        db.commit()
        db.close()
        return {"status": "Failed", "error": "Could not upload to S3"}
    
    # Update video with s3_key
    video = db.query(Video).filter(Video.id == video_id).first()
    if video:
        video.s3_key = s3_key
    db.commit()
    db.close()
    
    # Cleanup local file
    if os.path.exists(local_path):
        os.remove(local_path)
    
    # Process the video from S3
    return process_video_task(s3_key, video_id, user_id)


@celery_app.task(name="convert_to_shorts")
def convert_clip_to_shorts_task(clip_id: str, user_id: str):
    """
    Convert a clip to 9:16 shorts format (Instagram Reels / YouTube Shorts).
    
    Args:
        clip_id: UUID of the clip record
        user_id: User ID for organizing files in S3
    """
    from .utils import convert_to_shorts
    
    db = get_db_session()
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Get the clip from database
        clip = db.query(Clip).filter(Clip.id == clip_id).first()
        if not clip or not clip.s3_key:
            return {"status": "Failed", "error": "Clip not found or no S3 key"}
        
        # Download the original clip from S3
        local_input = os.path.join(temp_dir, clip.filename)
        if not download_file(clip.s3_key, local_input):
            return {"status": "Failed", "error": "Could not download clip from S3"}
        
        # Convert to shorts format
        shorts_filename = f"shorts_{clip.filename}"
        local_output = os.path.join(temp_dir, shorts_filename)
        convert_to_shorts(local_input, local_output)
        
        # Upload shorts version to S3
        shorts_s3_key = f"shorts/{user_id}/{clip.video_id}/{shorts_filename}"
        if not upload_file(local_output, shorts_s3_key):
            return {"status": "Failed", "error": "Could not upload shorts to S3"}
        
        # Update clip with shorts s3 key
        clip.shorts_s3_key = shorts_s3_key
        db.commit()
        
        return {
            "status": "Complete",
            "shorts_s3_key": shorts_s3_key,
            "filename": shorts_filename
        }
    
    except Exception as e:
        print(f"Error converting to shorts: {e}")
        return {"status": "Failed", "error": str(e)}
    
    finally:
        db.close()
        # Cleanup temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)