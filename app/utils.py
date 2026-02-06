import subprocess
import os
import re

def extract_unique_id(url):
    regex = r"(?:v=|/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match.group(1) if match else None

def create_video_clip(input_path, output_path, start, end):
    duration = end - start
    
    # FFmpeg Command Breakdown:
    # -i: Input file (placed BEFORE -ss for "Slow Seek" / accurate seeking)
    # -ss: Start time
    # -t: Duration
    # -c:v libx264: Re-encode video
    # -c:a aac: Re-encode audio
    # -preset fast: Using fast preset to mitigate slow seek time slightly
    command = [
        'ffmpeg', '-i', input_path, '-ss', str(start),
        '-t', str(duration), '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac', '-y', output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

def download_youtube_video(url, output_dir="uploads"):
    import yt_dlp
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{output_dir}/%(id)s.%(ext)s',
        'noplaylist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        video_id = info_dict.get("id", None)
        ext = info_dict.get("ext", "mp4")
        filename = f"{video_id}.{ext}" if video_id else None
        
    return filename


def get_video_dimensions(input_path):
    """Get video width and height using ffprobe."""
    command = [
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=s=x:p=0',
        input_path
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    width, height = map(int, result.stdout.strip().split('x'))
    return width, height


def convert_to_shorts(input_path, output_path):
    """
    Convert video to 9:16 aspect ratio (Instagram Reels / YouTube Shorts format).
    Crops the center of the video to fill the entire frame.
    No blur, no letterboxing - just center crop.
    """
    width, height = get_video_dimensions(input_path)
    
    # Target aspect ratio is 9:16 (portrait)
    target_ratio = 9 / 16
    current_ratio = width / height
    
    if current_ratio > target_ratio:
        # Video is wider than target - crop horizontally (take center)
        new_width = int(height * target_ratio)
        new_height = height
        x_offset = (width - new_width) // 2
        y_offset = 0
    else:
        # Video is taller or equal - crop vertically (take center)
        new_width = width
        new_height = int(width / target_ratio)
        x_offset = 0
        y_offset = (height - new_height) // 2
    
    # Ensure dimensions are even (required by many codecs)
    new_width = new_width - (new_width % 2)
    new_height = new_height - (new_height % 2)
    
    # FFmpeg crop filter: crop=out_w:out_h:x:y
    crop_filter = f"crop={new_width}:{new_height}:{x_offset}:{y_offset}"
    
    # Also scale to common shorts resolution (1080x1920 or proportional)
    # Using 1080 width as target for quality
    scale_filter = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    
    command = [
        'ffmpeg', '-i', input_path,
        '-vf', f'{crop_filter},{scale_filter}',
        '-c:v', 'libx264', '-preset', 'fast',
        '-c:a', 'aac',
        '-y', output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path