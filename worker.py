import os
import json
import logging
import redis
from dotenv import load_dotenv

from processor import process_job
from manifest import JobRequest

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("worker")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
QUEUE_NAME = os.getenv("QUEUE_NAME", "audio_preprocessing_jobs")
STATUS_QUEUE = os.getenv("STATUS_QUEUE", "audio_preprocessing_status")

def main():
    logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}, queue: {QUEUE_NAME}")
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    
    logger.info("Worker started, waiting for jobs...")
    while True:
        try:
            # Block until an item is available in the queue
            result = r.blpop(QUEUE_NAME, timeout=0)
            if not result:
                continue
                
            _, job_data_str = result
            logger.info(f"Received job payload: {job_data_str}")
            
            try:
                job_data = json.loads(job_data_str)
                job_req = JobRequest(**job_data)
                
                # Process
                manifest = process_job(job_req)
                
                # Report success
                status_msg = {
                    "job_id": job_req.job_id,
                    "status": "completed",
                    "manifest": manifest.model_dump()
                }
                r.lpush(STATUS_QUEUE, json.dumps(status_msg))
                
            except Exception as e:
                logger.exception("Error processing job")
                
                # Attempt to extract job_id for failure reporting
                job_id = "unknown"
                try:
                    parsed = json.loads(job_data_str)
                    job_id = parsed.get("job_id", "unknown")
                except:
                    pass
                    
                status_msg = {
                    "job_id": job_id,
                    "status": "failed",
                    "error": str(e)
                }
                r.lpush(STATUS_QUEUE, json.dumps(status_msg))
                
        except Exception as e:
            logger.error(f"Worker loop error: {e}")

if __name__ == "__main__":
    main()
