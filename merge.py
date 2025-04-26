from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import tempfile
from pydub import AudioSegment
import boto3  
import os

app = FastAPI()

# AWS S3 credentials 
s3 = boto3.client('s3', aws_access_key_id=os.environ.get("ACCESS_KEY_ID"), aws_secret_access_key=os.environ.get("SECRET_ACCESS_KEY"), region_name=os.environ.get("REGION"))

BUCKET_NAME = os.environ.get("BUCKET_NAME")

@app.post("/merge")
async def merge_audio(
    lyrics_audio: UploadFile = File(...)
):
    # Save uploaded lyrics to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as lyrics_temp:
        lyrics_temp.write(await lyrics_audio.read())
        lyrics_path = lyrics_temp.name

    beat_key = "beat.mp3" 
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as beat_temp:
        s3.download_fileobj(BUCKET_NAME, beat_key, beat_temp)
        beat_path = beat_temp.name

    # Load audio files
    lyrics = AudioSegment.from_file(lyrics_path)
    beat = AudioSegment.from_file(beat_path)

    # Make beat as long as lyrics
    if len(beat) < len(lyrics):
        beat = beat * (len(lyrics) // len(beat) + 1)
    beat = beat[:len(lyrics)]

    # Adjust volumes 
    lyrics = lyrics + 5
    beat = beat - 2

    # Merge the two files 
    combined = beat.overlay(lyrics)

    # Export merged audio to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as merged_temp:
        combined.export(merged_temp.name, format="mp3")
        merged_path = merged_temp.name

    # Upload merged audio to S3
    final_key = "merged_audio/final_song.mp3" 
    with open(merged_path, "rb") as f:
        s3.upload_fileobj(f, BUCKET_NAME, final_key)

    # Build the S3 URL
    s3_url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{final_key}"

    return JSONResponse({"merged_audio_url": s3_url})
