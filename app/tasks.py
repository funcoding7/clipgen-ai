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


def extract_clip_transcript(segments: list, start_time: float, end_time: float) -> list:
    """
    Extract transcript segments that fall within a clip's time range.
    Adjusts timestamps to be relative to the clip start.
    
    Args:
        segments: Full video transcript segments from Whisper
        start_time: Clip start time in seconds
        end_time: Clip end time in seconds
    
    Returns:
        List of segments with adjusted timestamps for the clip
    """
    clip_segments = []
    
    for seg in segments:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', 0)
        
        # Check if segment overlaps with clip time range
        if seg_end > start_time and seg_start < end_time:
            # Adjust timestamps to be relative to clip start
            adjusted_start = max(0, seg_start - start_time)
            adjusted_end = min(end_time - start_time, seg_end - start_time)
            
            clip_segments.append({
                'start': round(adjusted_start, 3),
                'end': round(adjusted_end, 3),
                'text': seg.get('text', '').strip()
            })
    
    return clip_segments

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
            
            # Extract transcript segments for this clip's time range
            clip_transcript = extract_clip_transcript(
                result["segments"], 
                clip['start'], 
                clip['end']
            )
            
            # Upload clip to S3
            clip_s3_key = f"clips/{user_id}/{video_id}/{clip_filename}"
            upload_success = upload_file(local_clip_path, clip_s3_key)
            
            if not upload_success:
                print(f"Warning: Failed to upload clip {clip_filename} to S3")
                continue
            
            # Save clip to database with S3 key, virality metadata, and transcript
            import json
            db_clip = Clip(
                video_id=video_id,
                filename=clip_filename,
                s3_key=clip_s3_key,
                reason=clip.get('reason', ''),
                start_time=clip['start'],
                end_time=clip['end'],
                virality_score=clip.get('virality_score'),
                hook_type=clip.get('hook_type'),
                transcript_json=json.dumps(clip_transcript) if clip_transcript else None
            )
            db.add(db_clip)
            created_clips.append({
                "file": clip_filename,
                "s3_key": clip_s3_key,
                "reason": clip.get('reason', ''),
                "virality_score": clip.get('virality_score'),
                "hook_type": clip.get('hook_type')
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
def convert_clip_to_shorts_task(clip_id: str, user_id: str, layout_type: str = "center_crop",
                                  enable_captions: bool = False, caption_style: str = "default"):
    """
    Convert a clip to 9:16 shorts format (Instagram Reels / YouTube Shorts).
    
    Args:
        clip_id: UUID of the clip record
        user_id: User ID for organizing files in S3
        layout_type: One of "center_crop", "blurred", "smart"
        enable_captions: Whether to burn in captions
        caption_style: Style preset for captions
    """
    from .utils import convert_to_shorts_with_layout
    
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
        
        # Generate captions file if enabled
        captions_file = None
        if enable_captions and clip.transcript_json:
            import json
            captions_file = os.path.join(temp_dir, "captions.srt")
            transcript_data = json.loads(clip.transcript_json)
            generate_srt_file(transcript_data, captions_file)
        
        # Convert to shorts format with layout and captions
        shorts_filename = f"shorts_{layout_type}_{clip.filename}"
        local_output = os.path.join(temp_dir, shorts_filename)
        convert_to_shorts_with_layout(
            local_input, 
            local_output, 
            layout_type=layout_type,
            captions_file=captions_file,
            caption_style=caption_style
        )
        
        # Upload shorts version to S3
        shorts_s3_key = f"shorts/{user_id}/{clip.video_id}/{shorts_filename}"
        if not upload_file(local_output, shorts_s3_key):
            return {"status": "Failed", "error": "Could not upload shorts to S3"}
        
        # Update clip with shorts s3 key and layout type
        clip.shorts_s3_key = shorts_s3_key
        clip.layout_type = layout_type
        db.commit()
        
        return {
            "status": "Complete",
            "shorts_s3_key": shorts_s3_key,
            "filename": shorts_filename,
            "layout_type": layout_type
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


def generate_srt_file(transcript_data: list, output_path: str):
    """
    Generate an SRT subtitle file from transcript data.
    
    Args:
        transcript_data: List of dicts with 'start', 'end', 'text' keys
        output_path: Path to write the SRT file
    """
    def format_timestamp(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(transcript_data, 1):
            start = format_timestamp(segment['start'])
            end = format_timestamp(segment['end'])
            text = segment.get('text', '').strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")