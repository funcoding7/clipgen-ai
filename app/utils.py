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


def convert_to_shorts_blurred(input_path, output_path):
    """
    Convert video to 9:16 with blurred background effect.
    The original video is scaled to fit in the center, with a blurred and 
    zoomed version of itself as the background. Great for preserving 
    full frame without cropping off subjects.
    """
    width, height = get_video_dimensions(input_path)
    
    # Target dimensions for shorts (1080x1920)
    target_w, target_h = 1080, 1920
    
    # Calculate scale factor to fit video in center while maintaining aspect ratio
    scale_factor = min(target_w / width, target_h / height)
    scaled_w = int(width * scale_factor)
    scaled_h = int(height * scale_factor)
    
    # Ensure even dimensions
    scaled_w = scaled_w - (scaled_w % 2)
    scaled_h = scaled_h - (scaled_h % 2)
    
    # Complex filter:
    # 1. Split input into two streams
    # 2. First stream: blur heavily, scale to fill 1080x1920, crop to exact size
    # 3. Second stream: scale to fit inside 1080x1920
    # 4. Overlay the clear video on top of blurred background
    filter_complex = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,boxblur=20:5[blurred];"
        f"[fg]scale={scaled_w}:{scaled_h}[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2[outv]"
    )
    
    command = [
        'ffmpeg', '-i', input_path,
        '-filter_complex', filter_complex,
        '-map', '[outv]', '-map', '0:a?',
        '-c:v', 'libx264', '-preset', 'fast',
        '-c:a', 'aac',
        '-y', output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path


def convert_to_shorts_with_layout(input_path, output_path, layout_type="center_crop", 
                                   captions_file=None, caption_style="default"):
    """
    Master function to convert video to shorts with different layout options.
    
    Args:
        input_path: Path to source video
        output_path: Path for output shorts video
        layout_type: One of "center_crop", "blurred", or "smart"
        captions_file: Optional path to SRT/ASS file for burned-in captions
        caption_style: Caption style preset (default, hormozi, capcut, minimal)
    
    Returns:
        Path to the output file
    """
    # First, apply the layout conversion
    if layout_type == "blurred":
        convert_to_shorts_blurred(input_path, output_path)
    elif layout_type == "smart":
        # Use AI-powered face tracking for smart cropping
        from .face_tracking import convert_to_shorts_smart
        convert_to_shorts_smart(input_path, output_path)
    else:
        # Default: center_crop
        convert_to_shorts(input_path, output_path)
    
    # If captions provided, burn them in
    if captions_file and os.path.exists(captions_file):
        temp_output = output_path + ".temp.mp4"
        os.rename(output_path, temp_output)
        burn_captions(temp_output, output_path, captions_file, caption_style)
        os.remove(temp_output)
    
    return output_path


def burn_captions(input_path, output_path, captions_file, style="default"):
    """
    Burn captions/subtitles into video using FFmpeg.
    
    Args:
        input_path: Path to source video
        output_path: Path for output video with captions
        captions_file: Path to SRT or ASS subtitle file
        style: Caption style preset
    
    Returns:
        Path to output file
    """
    # Escape special characters in file path for FFmpeg
    escaped_captions = captions_file.replace(":", "\\:").replace("'", "\\'")
    
    # Style presets for subtitles filter
    style_configs = {
        "default": "FontSize=24,FontName=Arial,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2",
        "hormozi": "FontSize=32,FontName=Impact,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=3,Bold=1",
        "capcut": "FontSize=28,FontName=Montserrat,PrimaryColour=&H00FFFF,OutlineColour=&H000000,Outline=2,Bold=1",
        "minimal": "FontSize=22,FontName=Helvetica,PrimaryColour=&HFFFFFF,OutlineColour=&H80000000,Outline=1"
    }
    
    force_style = style_configs.get(style, style_configs["default"])
    
    # Use subtitles filter for SRT, or ass filter for ASS files
    if captions_file.endswith('.ass'):
        subtitle_filter = f"ass='{escaped_captions}'"
    else:
        subtitle_filter = f"subtitles='{escaped_captions}':force_style='{force_style}'"
    
    command = [
        'ffmpeg', '-i', input_path,
        '-vf', subtitle_filter,
        '-c:v', 'libx264', '-preset', 'fast',
        '-c:a', 'copy',
        '-y', output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path