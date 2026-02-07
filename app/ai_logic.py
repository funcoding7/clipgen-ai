# app/ai_logic.py
from google import genai
from google.genai import types
import json
import os
import pydantic
from typing import Literal
from enum import Enum


class HookType(str, Enum):
    """Categories of viral hooks"""
    STRONG_HOOK = "Strong Hook"
    EMOTIONAL_PAYOFF = "Emotional Payoff"
    CONTROVERSIAL = "Controversial Statement"
    SURPRISING_FACT = "Surprising Fact"
    STORY_PEAK = "Story Peak"
    HUMOR = "Humor"
    CALL_TO_ACTION = "Call to Action"
    CLIFFHANGER = "Cliffhanger"


def identify_viral_clips(transcript_segments):
    """
    Analyze transcript and identify viral clip opportunities with scoring.
    Returns clips sorted by virality score (highest first).
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    # Flatten segments into a readable string for the LLM
    text_content = "\n".join([
        f"{s['start']} - {s['end']}: {s['text']}" 
        for s in transcript_segments
    ])

    prompt = f"""
    You are an elite social media content strategist who has analyzed millions of viral TikTok and Reels videos.
    
    Analyze the following transcript from a video and identify the TOP 5 most viral-worthy moments.
    
    For each clip:
    1. It must be between 20-30 seconds long
    2. It must be completely self-contained (viewers can understand it without context)
    3. Rate its VIRALITY SCORE from 0-100 based on:
       - Hook strength (does it grab attention in first 3 seconds?)
       - Emotional resonance (does it make viewers feel something?)
       - Shareability (would someone tag a friend or repost?)
       - Controversy/curiosity factor (does it spark debate or questions?)
       - Completion likelihood (will viewers watch till the end?)
    
    4. Classify the HOOK TYPE as one of:
       - "Strong Hook" - Attention-grabbing opening statement
       - "Emotional Payoff" - Heartwarming or tear-jerking moment
       - "Controversial Statement" - Opinion that sparks debate
       - "Surprising Fact" - Unexpected information or reveal
       - "Story Peak" - Climax of a narrative
       - "Humor" - Genuinely funny moment
       - "Call to Action" - Motivational or inspiring content
       - "Cliffhanger" - Creates curiosity for more
    
    CRITICAL: Ensure start/end times capture the COMPLETE hook including setup.
    
    Transcript:
    {text_content}
    """
    
    # Define the schema for structured output using Pydantic
    class Clip(pydantic.BaseModel):
        start: float
        end: float
        reason: str
        virality_score: int = pydantic.Field(ge=0, le=100, description="Virality score from 0-100")
        hook_type: str = pydantic.Field(description="Category of viral hook")
        
    class ClipsResponse(pydantic.BaseModel):
        clips: list[Clip]

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClipsResponse
        )
    )
    
    # Parse the response
    if response.parsed:
        clips = response.parsed.model_dump()['clips']
    else:
        data = json.loads(response.text)
        clips = data["clips"] if isinstance(data, dict) and "clips" in data else data
    
    # Sort by virality score (highest first)
    clips.sort(key=lambda x: x.get('virality_score', 0), reverse=True)
    
    return clips


def identify_viral_clips_multimodal(transcript_segments, frame_paths: list[str]):
    """
    Analyze both transcript AND video frames to identify viral clips.
    Uses visual cues (reactions, action, b-roll quality) in addition to dialogue.
    
    Args:
        transcript_segments: List of transcript segments with timestamps
        frame_paths: List of paths to sampled video frames (1fps recommended)
    
    Returns:
        List of clips with virality scores, sorted by score descending
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    # Flatten segments into a readable string
    text_content = "\n".join([
        f"{s['start']} - {s['end']}: {s['text']}" 
        for s in transcript_segments
    ])
    
    # Build multimodal content - include frames
    contents = []
    
    # Add transcript context
    contents.append(f"""
    You are an elite social media content strategist analyzing a video for viral potential.
    
    I'm providing you with:
    1. The full transcript with timestamps
    2. Sampled frames from the video (1 frame per second)
    
    Identify the TOP 5 most viral-worthy moments. Consider BOTH:
    - Audio/dialogue hooks (what's being said)
    - Visual hooks (reactions, action, high-quality b-roll, emotional expressions)
    
    A moment with weak dialogue but STRONG visual content (funny reaction, impressive action) 
    should score highly. Don't just rely on words.
    
    For each clip (20-30 seconds):
    - virality_score (0-100): Based on hook strength, emotion, shareability, visual appeal
    - hook_type: One of "Strong Hook", "Emotional Payoff", "Controversial Statement", 
                 "Surprising Fact", "Story Peak", "Humor", "Call to Action", "Cliffhanger"
    - reason: Why this clip will go viral
    
    Transcript:
    {text_content}
    
    Now analyzing the video frames (in chronological order):
    """)
    
    # Add frames (limit to avoid token limits)
    max_frames = 30  # Sample key frames
    step = max(1, len(frame_paths) // max_frames)
    for i, frame_path in enumerate(frame_paths[::step]):
        if os.path.exists(frame_path):
            # Add frame with timestamp context
            with open(frame_path, 'rb') as f:
                frame_data = f.read()
            contents.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": frame_data
                }
            })
            contents.append(f"[Frame at ~{i * step} seconds]")
    
    # Define schema
    class Clip(pydantic.BaseModel):
        start: float
        end: float
        reason: str
        virality_score: int = pydantic.Field(ge=0, le=100)
        hook_type: str
        
    class ClipsResponse(pydantic.BaseModel):
        clips: list[Clip]

    response = client.models.generate_content(
        model="gemini-2.0-flash",  # Using multimodal-capable model
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClipsResponse
        )
    )
    
    if response.parsed:
        clips = response.parsed.model_dump()['clips']
    else:
        data = json.loads(response.text)
        clips = data["clips"] if isinstance(data, dict) and "clips" in data else data
    
    clips.sort(key=lambda x: x.get('virality_score', 0), reverse=True)
    
    return clips