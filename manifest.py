from pydantic import BaseModel, Field
from typing import List, Optional

class JobOptions(BaseModel):
    target_sample_rate: int = 16000
    channels: int = 1
    chunk_minutes: int = 10
    overlap_seconds: int = 3

class JobRequest(BaseModel):
    job_id: str
    input_path: str
    output_path: str
    language: Optional[str] = None
    options: JobOptions = Field(default_factory=JobOptions)

class SourceInfo(BaseModel):
    path: str
    duration_seconds: float
    format: str
    sample_rate: int
    channels: int
    bitrate: Optional[int] = None

class NormalizedInfo(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    codec: str = "pcm_s16le"

class ChunkInfo(BaseModel):
    index: int
    path: str
    start: float
    end: float
    duration: float
    overlap_start: float
    overlap_end: float

class JobManifest(BaseModel):
    job_id: str
    source: SourceInfo
    normalized: NormalizedInfo
    chunks: List[ChunkInfo]
