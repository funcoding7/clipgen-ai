# app/ai_logic.py
from google import genai
from google.genai import types
import json
import os
import pydantic

def identify_viral_clips(transcript_segments):
        
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    # Flatten segments into a readable string for the LLM
    text_content = "\n".join([
        f"{s['start']} - {s['end']}: {s['text']}" 
        for s in transcript_segments
    ])

    prompt = f"""
    You are a professional social media editor. Analyze the following transcript from a video.
    Identify the 5 most engaging, self-contained "hooks" or highlights suitable for a TikTok/Reel.
    Each clip must be between 20 and 30 seconds long.
    Ensure that the entire hook is captured in the start and end times.
    Transcript:
    {text_content}
    """
    
    # Define the schema for structured output using Pydantic
    class Clip(pydantic.BaseModel):
        start: float
        end: float
        reason: str
        
    class ClipsResponse(pydantic.BaseModel):
        clips: list[Clip]

    response = client.models.generate_content(
        model="gemini-2.5-flash", # Using latest flash model
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClipsResponse
        )
    )
    
    # Parse the response
    # The new SDK might return a parsed object if schema is provided, check docs or assume dict
    # If response.parsed is available, use it. Otherwise parse result.text
    
    if response.parsed:
        return response.parsed.model_dump()['clips']
    
    data = json.loads(response.text)
    if isinstance(data, dict) and "clips" in data:
        return data["clips"]
    return data