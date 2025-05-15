from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import tempfile
from pydub import AudioSegment
import boto3  
import os
from dotenv import load_dotenv
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# AWS S3 credentials 
try:
    s3 = boto3.client('s3', 
        aws_access_key_id=os.environ.get("ACCESS_KEY_ID"), 
        aws_secret_access_key=os.environ.get("SECRET_ACCESS_KEY"), 
        region_name=os.environ.get("REGION")
    )
    BUCKET_NAME = os.environ.get("BUCKET_NAME")
    if not all([os.environ.get("ACCESS_KEY_ID"), os.environ.get("SECRET_ACCESS_KEY"), os.environ.get("REGION"), BUCKET_NAME]):
        raise ValueError("Missing required AWS credentials")
except Exception as e:
    logger.error(f"Failed to initialize AWS S3 client: {str(e)}")
    raise

@app.post("/merge")
async def merge_audio(
    lyrics_audio: UploadFile = File(...)
):
    try:
        logger.info("Starting audio merge process")
        
        # Save uploaded lyrics to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as lyrics_temp:
            content = await lyrics_audio.read()
            logger.info(f"Received audio file of size: {len(content)} bytes")
            lyrics_temp.write(content)
            lyrics_path = lyrics_temp.name
            logger.info(f"Saved lyrics audio to temp file: {lyrics_path}")

        beat_key = "beat.mp3" 
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as beat_temp:
                logger.info(f"Downloading beat file from S3: {beat_key}")
                s3.download_fileobj(BUCKET_NAME, beat_key, beat_temp)
                beat_path = beat_temp.name
                logger.info(f"Downloaded beat file to: {beat_path}")
        except Exception as e:
            logger.error(f"Failed to download beat file from S3: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to download beat file")

        try:
            # Load audio files
            logger.info("Loading audio files")
            lyrics = AudioSegment.from_file(lyrics_path)
            beat = AudioSegment.from_file(beat_path)
            logger.info(f"Lyrics duration: {len(lyrics)}ms, Beat duration: {len(beat)}ms")
        except Exception as e:
            logger.error(f"Failed to load audio files: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to load audio files")

        # Make beat as long as lyrics
        if len(beat) < len(lyrics):
            logger.info("Extending beat to match lyrics length")
            beat = beat * (len(lyrics) // len(beat) + 1)
        beat = beat[:len(lyrics)]

        # Adjust volumes 
        logger.info("Adjusting audio volumes")
        lyrics = lyrics + 5
        beat = beat - 2

        # Merge the two files 
        logger.info("Merging audio files")
        combined = beat.overlay(lyrics)

        # Export merged audio to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as merged_temp:
            logger.info("Exporting merged audio")
            combined.export(merged_temp.name, format="mp3")
            merged_path = merged_temp.name
            logger.info(f"Exported merged audio to: {merged_path}")

        # Upload merged audio to S3 w/ unique identifier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_key = f"merged_audio/test_final_song_{timestamp}.mp3"
        try:
            logger.info(f"Uploading merged audio to S3: {final_key}")
            with open(merged_path, "rb") as f:
                s3.upload_fileobj(f, BUCKET_NAME, final_key)
            logger.info("Successfully uploaded to S3")
        except Exception as e:
            logger.error(f"Failed to upload to S3: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to upload merged audio")

        # Build the S3 URL
        s3_url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{final_key}"
        logger.info(f"Generated S3 URL: {s3_url}")

        # Cleanup temporary files
        try:
            os.remove(lyrics_path)
            os.remove(beat_path)
            os.remove(merged_path)
            logger.info("Cleaned up temporary files")
        except Exception as e:
            logger.warning(f"Failed to cleanup temporary files: {str(e)}")

        return JSONResponse({"merged_audio_url": s3_url})

    except Exception as e:
        logger.error(f"Unexpected error in merge_audio: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
