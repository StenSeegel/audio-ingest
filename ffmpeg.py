import subprocess
import json
import logging
import math
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

def get_metadata(file_path: str) -> Dict[str, Any]:
    """Runs ffprobe and returns metadata."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)

def get_audio_info(file_path: str) -> Dict[str, Any]:
    """Extracts relevant audio information from ffprobe output."""
    metadata = get_metadata(file_path)
    
    format_info = metadata.get("format", {})
    streams = metadata.get("streams", [])
    
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    
    if not audio_stream:
        raise ValueError(f"No audio stream found in {file_path}")
        
    duration = float(format_info.get("duration", 0) or audio_stream.get("duration", 0))
    sample_rate = int(audio_stream.get("sample_rate", 0))
    channels = int(audio_stream.get("channels", 0))
    bitrate = int(format_info.get("bit_rate", 0) or audio_stream.get("bit_rate", 0))
    
    # Optional: codec_name
    codec = audio_stream.get("codec_name", "")
    
    return {
        "duration_seconds": duration,
        "sample_rate": sample_rate,
        "channels": channels,
        "bitrate": bitrate,
        "codec": codec,
    }

def normalize_audio(input_path: str, output_path: str, sample_rate: int = 16000, channels: int = 1):
    """Converts audio to mono 16kHz PCM WAV."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", str(channels),
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        output_path
    ]
    
    logger.info(f"Running ffmpeg normalize: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr}")
        raise RuntimeError(f"FFmpeg normalization failed with exit code {result.returncode}")

def split_into_chunks(input_path: str, output_dir: str, duration_seconds: float, chunk_minutes: int = 10, overlap_seconds: int = 3) -> List[Dict[str, Any]]:
    """Splits audio into chunks with overlap, returning list of chunk infos."""
    chunk_duration_sec = chunk_minutes * 60
    chunks = []
    
    current_start = 0.0
    index = 0
    
    while current_start < duration_seconds:
        # Calculate actual end and overlap
        chunk_end = min(current_start + chunk_duration_sec, duration_seconds)
        
        # If this is not the last chunk, add overlap to the end
        actual_end = min(chunk_end + overlap_seconds, duration_seconds) if chunk_end < duration_seconds else duration_seconds
        
        chunk_filename = f"chunk_{index:03d}.wav"
        chunk_path = f"{output_dir}/{chunk_filename}"
        
        actual_duration = actual_end - current_start
        
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(current_start),
            "-t", str(actual_duration),
            "-i", input_path,
            "-c", "copy",
            chunk_path
        ]
        
        logger.info(f"Running ffmpeg split for chunk {index}: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"FFmpeg chunking failed for {chunk_filename}")
            
        # Calculate overlaps
        overlap_start = overlap_seconds if index > 0 else 0.0
        overlap_end = overlap_seconds if actual_end < duration_seconds else 0.0
            
        chunks.append({
            "index": index,
            "filename": chunk_filename,
            "local_path": chunk_path,
            "start": current_start,
            "end": actual_end,
            "duration": actual_duration,
            "overlap_start": float(overlap_start),
            "overlap_end": float(overlap_end)
        })
        
        current_start = chunk_end
        index += 1
        
    return chunks
