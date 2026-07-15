import os
import json
import logging
import time
import redis
import socket
from dotenv import load_dotenv

from processor import process_job
from manifest import JobRequest

load_dotenv()

WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())

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
        decode_responses=True,
        socket_keepalive=True,
        health_check_interval=30
    )

    logger.info("Worker started, waiting for jobs...")
    error_backoff = 1
    while True:
        try:
            # Block until an item is available in the queue. A finite timeout
            # (instead of 0 = forever) lets the loop survive half-open
            # connections and keeps the idle cost at one request per 30s.
            result = r.blpop(QUEUE_NAME, timeout=30)
            error_backoff = 1
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
                    "worker_id": WORKER_ID,
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
                    "worker_id": WORKER_ID,
                    "error": str(e)
                }
                r.lpush(STATUS_QUEUE, json.dumps(status_msg))
                
        except Exception as e:
            # Without a pause, a dead Redis connection turns this loop into a
            # 100% CPU spin (observed: 6 days at ~98% of a core). Back off
            # exponentially up to 30s; redis-py reconnects on the next call.
            logger.error(f"Worker loop error: {e} (retrying in {error_backoff}s)")
            time.sleep(error_backoff)
            error_backoff = min(error_backoff * 2, 30)

if __name__ == "__main__":
    main()
