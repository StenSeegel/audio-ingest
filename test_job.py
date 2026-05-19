import os
import json
import uuid
import time
import redis
import boto3
from dotenv import load_dotenv

load_dotenv()

# Config
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
QUEUE_NAME = os.getenv("QUEUE_NAME", "audio_preprocessing_jobs")
STATUS_QUEUE = os.getenv("STATUS_QUEUE", "audio_preprocessing_status")

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
BUCKET_NAME = "audio-ingest"

TEST_FILE_PATH = os.path.join(os.path.dirname(__file__), "tests", "mockup_22MB.mp3")

def main():
    print("1. Connecting to local Redis & MinIO...")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION
    )

    job_id = str(uuid.uuid4())
    s3_input_key = f"test-inputs/{job_id}/original.mp3"
    s3_input_uri = f"s3://{BUCKET_NAME}/{s3_input_key}"
    s3_output_uri = f"s3://{BUCKET_NAME}/jobs/{job_id}/"

    print(f"2. Uploading {TEST_FILE_PATH} to {s3_input_uri}...")
    try:
        s3.upload_file(TEST_FILE_PATH, BUCKET_NAME, s3_input_key)
    except Exception as e:
        print(f"Failed to upload file: {e}")
        return

    print("3. Pushing job to Redis queue...")
    job_payload = {
        "job_id": job_id,
        "input_path": s3_input_uri,
        "output_path": s3_output_uri,
        "language": "de",
        "options": {
            "target_sample_rate": 16000,
            "channels": 1,
            "chunk_minutes": 10,
            "overlap_seconds": 3
        }
    }
    r.lpush(QUEUE_NAME, json.dumps(job_payload))

    print(f"4. Job {job_id} dispatched. Waiting for result in {STATUS_QUEUE}...")
    
    # We will loop and check for our specific job ID, ignoring others if they exist
    start_time = time.time()
    while True:
        # Wait up to 5 seconds per iteration
        result = r.blpop(STATUS_QUEUE, timeout=5)
        if result:
            _, status_str = result
            status_data = json.loads(status_str)
            if status_data.get("job_id") == job_id:
                print("\n=== Result Received! ===")
                print(json.dumps(status_data, indent=2))
                break
            else:
                print(f"Received status for different job: {status_data.get('job_id')}. Re-queueing...")
                r.lpush(STATUS_QUEUE, status_str)
        
        elapsed = time.time() - start_time
        if elapsed > 120:  # 2 minutes timeout
            print("Timeout waiting for job completion.")
            break

if __name__ == "__main__":
    main()
