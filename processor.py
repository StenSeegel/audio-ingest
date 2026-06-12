import os
import shutil
import logging
from typing import Dict, Any

from storage import download_file, upload_file
from ffmpeg import get_audio_info, normalize_audio, split_into_chunks
from manifest import JobRequest, JobManifest, SourceInfo, NormalizedInfo, ChunkInfo

logger = logging.getLogger(__name__)

def process_job(job_req: JobRequest) -> JobManifest:
    work_dir = f"/tmp/{job_req.job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        # 1. Download
        logger.info(f"Downloading {job_req.input_path}")
        original_ext = os.path.splitext(job_req.input_path)[1] or '.audio'
        local_original = os.path.join(work_dir, f"original{original_ext}")
        download_file(job_req.input_path, local_original)
        
        # 2. Extract Metadata
        logger.info("Extracting metadata")
        audio_info = get_audio_info(local_original)
        source_info = SourceInfo(
            path=job_req.input_path,
            duration_seconds=audio_info["duration_seconds"],
            format=original_ext.lstrip('.'),
            sample_rate=audio_info["sample_rate"],
            channels=audio_info["channels"],
            bitrate=audio_info["bitrate"]
        )
        
        # 3. Normalize
        logger.info("Normalizing audio")
        local_normalized = os.path.join(work_dir, "normalized.wav")
        normalize_audio(
            local_original, 
            local_normalized,
            sample_rate=job_req.options.target_sample_rate,
            channels=job_req.options.channels
        )
        
        normalized_info = NormalizedInfo(
            sample_rate=job_req.options.target_sample_rate,
            channels=job_req.options.channels,
            codec="pcm_s16le"
        )
        
        # 4. Chunking
        logger.info("Splitting into chunks")
        chunks_dir = os.path.join(work_dir, "chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        
        chunk_results = split_into_chunks(
            local_normalized,
            chunks_dir,
            duration_seconds=source_info.duration_seconds,
            chunk_minutes=job_req.options.chunk_minutes,
            overlap_seconds=job_req.options.overlap_seconds
        )
        
        # 5. Upload chunks and build manifest chunks list
        logger.info("Uploading chunks")
        manifest_chunks = []
        for c in chunk_results:
            s3_chunk_path = f"{job_req.output_path}/chunks/{c['filename']}"
            if job_req.output_path.endswith('/'):
                s3_chunk_path = f"{job_req.output_path}chunks/{c['filename']}"
                
            upload_file(c['local_path'], s3_chunk_path)
            
            manifest_chunks.append(ChunkInfo(
                index=c["index"],
                path=s3_chunk_path,
                start=c["start"],
                end=c["end"],
                duration=c["duration"],
                overlap_start=c["overlap_start"],
                overlap_end=c["overlap_end"]
            ))
            
        # 6. Extract base64 snippets if requested
        extracted_snippets = None
        if job_req.options.extract_snippets:
            logger.info("Extracting base64 audio snippets")
            extracted_snippets = {}
            from ffmpeg import extract_base64_snippet
            for snippet in job_req.options.extract_snippets:
                sp_id = snippet.get("id")
                start = snippet.get("start", 0.0)
                end = snippet.get("end", 0.0)
                if sp_id and end > start:
                    try:
                        b64 = extract_base64_snippet(local_normalized, start, end)
                        extracted_snippets[sp_id] = b64
                    except Exception as e:
                        logger.error(f"Failed to extract snippet for {sp_id}: {e}")
        
        # 7. Generate and upload manifest
        logger.info("Generating manifest")
        manifest = JobManifest(
            job_id=job_req.job_id,
            source=source_info,
            normalized=normalized_info,
            chunks=manifest_chunks,
            extracted_snippets=extracted_snippets
        )
        
        local_manifest = os.path.join(work_dir, "manifest.json")
        with open(local_manifest, "w") as f:
            f.write(manifest.model_dump_json(indent=2))
            
        s3_manifest_path = f"{job_req.output_path}/manifest.json"
        if job_req.output_path.endswith('/'):
            s3_manifest_path = f"{job_req.output_path}manifest.json"
            
        upload_file(local_manifest, s3_manifest_path)
        
        logger.info(f"Job {job_req.job_id} completed successfully")
        return manifest
        
    finally:
        logger.info(f"Cleaning up {work_dir}")
        shutil.rmtree(work_dir, ignore_errors=True)
