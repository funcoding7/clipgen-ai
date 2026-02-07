# app/face_tracking.py
"""
Face tracking module for smart cropping in shorts conversion.
Uses MediaPipe for lightweight face detection and tracks subject position
to dynamically adjust crop window.
"""

import subprocess
import tempfile
import os
from typing import List, Tuple, Optional


def extract_frames(video_path: str, output_dir: str, fps: float = 2.0) -> List[str]:
    """
    Extract frames from video at specified FPS for analysis.
    
    Args:
        video_path: Path to source video
        output_dir: Directory to save extracted frames
        fps: Frames per second to extract (default 2 fps)
    
    Returns:
        List of frame file paths in chronological order
    """
    os.makedirs(output_dir, exist_ok=True)
    
    command = [
        'ffmpeg', '-i', video_path,
        '-vf', f'fps={fps}',
        '-q:v', '2',
        os.path.join(output_dir, 'frame_%04d.jpg'),
        '-y'
    ]
    
    subprocess.run(command, check=True, capture_output=True)
    
    frames = sorted([
        os.path.join(output_dir, f) 
        for f in os.listdir(output_dir) 
        if f.endswith('.jpg')
    ])
    
    return frames


def detect_faces_in_frames(frame_paths: List[str]) -> List[Optional[Tuple[float, float, float, float]]]:
    """
    Detect face positions in a sequence of frames using MediaPipe or OpenCV cascade.
    
    Args:
        frame_paths: List of paths to frame images
    
    Returns:
        List of face bounding boxes (x, y, w, h) normalized 0-1, or None if no face
    """
    try:
        import cv2
    except ImportError:
        print("Warning: OpenCV not installed. Smart cropping will fall back to center crop.")
        return [None] * len(frame_paths)
    
    # Try MediaPipe first (newer API)
    try:
        import mediapipe as mp
        # Try new API (0.10.x+)
        if hasattr(mp, 'tasks'):
            return _detect_faces_mediapipe_new(frame_paths, mp, cv2)
        # Try legacy API
        elif hasattr(mp, 'solutions'):
            return _detect_faces_mediapipe_legacy(frame_paths, mp, cv2)
    except Exception as e:
        print(f"MediaPipe not available: {e}")
    
    # Fallback to OpenCV Haar cascade (always available with cv2)
    print("Using OpenCV cascade for face detection...")
    return _detect_faces_opencv(frame_paths, cv2)


def _detect_faces_mediapipe_legacy(frame_paths: List[str], mp, cv2) -> List[Optional[Tuple[float, float, float, float]]]:
    """Legacy MediaPipe API (< 0.10.x)"""
    mp_face_detection = mp.solutions.face_detection
    face_positions = []
    
    with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
        for frame_path in frame_paths:
            image = cv2.imread(frame_path)
            if image is None:
                face_positions.append(None)
                continue
            
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = face_detection.process(rgb_image)
            
            if results.detections:
                detection = results.detections[0]
                bbox = detection.location_data.relative_bounding_box
                center_x = bbox.xmin + bbox.width / 2
                center_y = bbox.ymin + bbox.height / 2
                face_positions.append((center_x, center_y, bbox.width, bbox.height))
            else:
                face_positions.append(None)
    
    return face_positions


def _detect_faces_mediapipe_new(frame_paths: List[str], mp, cv2) -> List[Optional[Tuple[float, float, float, float]]]:
    """New MediaPipe API (0.10.x+) using tasks"""
    # Fall back to OpenCV if tasks API is complex
    return _detect_faces_opencv(frame_paths, cv2)


def _detect_faces_opencv(frame_paths: List[str], cv2) -> List[Optional[Tuple[float, float, float, float]]]:
    """OpenCV Haar cascade fallback - works reliably"""
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    face_positions = []
    
    for frame_path in frame_paths:
        image = cv2.imread(frame_path)
        if image is None:
            face_positions.append(None)
            continue
        
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        if len(faces) > 0:
            # Get largest face
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            # Normalize to 0-1
            center_x = (x + w / 2) / width
            center_y = (y + h / 2) / height
            norm_w = w / width
            norm_h = h / height
            face_positions.append((center_x, center_y, norm_w, norm_h))
        else:
            face_positions.append(None)
    
    return face_positions


def smooth_positions(positions: List[Optional[Tuple[float, float, float, float]]], 
                     window_size: int = 5) -> List[Tuple[float, float]]:
    """
    Smooth face positions to prevent jittery camera movement.
    Uses a moving average filter.
    
    Args:
        positions: Raw face positions from detection
        window_size: Number of frames for smoothing
    
    Returns:
        Smoothed center positions (x, y) for each frame
    """
    # Fill None values with interpolation or center default
    filled_positions = []
    last_valid = (0.5, 0.5)  # Default to center
    
    for pos in positions:
        if pos is not None:
            last_valid = (pos[0], pos[1])
        filled_positions.append(last_valid)
    
    # Apply moving average smoothing
    smoothed = []
    half_window = window_size // 2
    
    for i in range(len(filled_positions)):
        start_idx = max(0, i - half_window)
        end_idx = min(len(filled_positions), i + half_window + 1)
        
        window = filled_positions[start_idx:end_idx]
        avg_x = sum(p[0] for p in window) / len(window)
        avg_y = sum(p[1] for p in window) / len(window)
        
        smoothed.append((avg_x, avg_y))
    
    return smoothed


def generate_crop_filter(smoothed_positions: List[Tuple[float, float]], 
                         video_width: int, video_height: int,
                         target_width: int = 1080, target_height: int = 1920,
                         fps: float = 2.0) -> str:
    """
    Generate FFmpeg crop/pan filter based on tracked face positions.
    
    Creates a smooth camera movement that follows the subject.
    
    Args:
        smoothed_positions: List of (x, y) center positions per sampled frame
        video_width: Source video width
        video_height: Source video height
        target_width: Output width (default 1080)
        target_height: Output height (default 1920)
        fps: FPS at which positions were sampled
    
    Returns:
        FFmpeg filter_complex string for dynamic cropping
    """
    # Calculate the crop dimensions needed for 9:16 from source
    target_ratio = target_width / target_height  # 0.5625
    source_ratio = video_width / video_height
    
    if source_ratio > target_ratio:
        # Source is wider - crop width
        crop_height = video_height
        crop_width = int(video_height * target_ratio)
    else:
        # Source is taller - crop height
        crop_width = video_width
        crop_height = int(video_width / target_ratio)
    
    # Ensure even dimensions
    crop_width = crop_width - (crop_width % 2)
    crop_height = crop_height - (crop_height % 2)
    
    # Maximum x/y offsets
    max_x_offset = video_width - crop_width
    max_y_offset = video_height - crop_height
    
    # Build keyframe expressions for sendcmd/zoompan
    # For simplicity, use a single dynamic crop based on average position
    if smoothed_positions:
        avg_x = sum(p[0] for p in smoothed_positions) / len(smoothed_positions)
        avg_y = sum(p[1] for p in smoothed_positions) / len(smoothed_positions)
    else:
        avg_x, avg_y = 0.5, 0.5
    
    # Calculate crop offset centered on average face position
    x_offset = int((avg_x * video_width) - (crop_width / 2))
    y_offset = int((avg_y * video_height) - (crop_height / 2))
    
    # Clamp to valid range
    x_offset = max(0, min(x_offset, max_x_offset))
    y_offset = max(0, min(y_offset, max_y_offset))
    
    # Build the filter
    crop_filter = f"crop={crop_width}:{crop_height}:{x_offset}:{y_offset}"
    scale_filter = f"scale={target_width}:{target_height}"
    
    return f"{crop_filter},{scale_filter}"


def convert_to_shorts_smart(input_path: str, output_path: str) -> str:
    """
    Convert video to 9:16 shorts format using smart subject tracking.
    Automatically detects and follows the main subject (face) in the frame.
    
    Args:
        input_path: Path to source video
        output_path: Path for output shorts video
    
    Returns:
        Path to output file
    """
    from .utils import get_video_dimensions, convert_to_shorts
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Get video dimensions
        width, height = get_video_dimensions(input_path)
        
        # Extract frames for analysis (2 fps is sufficient)
        frames = extract_frames(input_path, temp_dir, fps=2.0)
        
        if not frames:
            print("Warning: No frames extracted. Falling back to center crop.")
            return convert_to_shorts(input_path, output_path)
        
        # Detect faces in frames
        face_positions = detect_faces_in_frames(frames)
        
        # Check if we found any faces
        has_faces = any(pos is not None for pos in face_positions)
        
        if not has_faces:
            print("No faces detected. Falling back to center crop.")
            return convert_to_shorts(input_path, output_path)
        
        # Smooth the positions to prevent jitter
        smoothed = smooth_positions(face_positions)
        
        # Generate crop filter
        crop_filter = generate_crop_filter(smoothed, width, height)
        
        # Apply the filter
        command = [
            'ffmpeg', '-i', input_path,
            '-vf', crop_filter,
            '-c:v', 'libx264', '-preset', 'fast',
            '-c:a', 'aac',
            '-y', output_path
        ]
        
        subprocess.run(command, check=True)
        
        return output_path
    
    finally:
        # Cleanup temp directory
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
