from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field


class DuplicateAction(str, Enum):
    KEEP = "keep"
    DELETE = "delete"
    FAVORITE = "favorite"
    DECIDE_LATER = "decide_later"


class ScanStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# Request Models
class ScanRequest(BaseModel):
    folder_path: str = Field(..., description="Path to the folder containing photos")
    include_subfolders: bool = Field(default=True, description="Whether to scan subfolders")


class DateQueryRequest(BaseModel):
    year: Optional[int] = Field(None, ge=1900, le=2100, description="Year to filter by")
    month: Optional[int] = Field(None, ge=1, le=12, description="Month to filter by (1-12)")
    day: Optional[int] = Field(None, ge=1, le=31, description="Day to filter by (1-31)")


class DuplicateActionRequest(BaseModel):
    action: DuplicateAction
    file_ids: List[int] = Field(..., description="List of file IDs to apply action to")
    keep_file_id: Optional[int] = Field(None, description="File ID to keep when deleting duplicates")


class OrganizeRequest(BaseModel):
    folder_path: str = Field(..., description="Path to the folder to organize")
    dry_run: bool = Field(default=False, description="Preview changes without moving files")


# Response Models
class MediaFileResponse(BaseModel):
    id: int
    file_path: str
    filename: str
    file_size: int
    date_taken: Optional[datetime]
    year: Optional[int]
    month: Optional[int]
    day: Optional[int]
    is_favorite: bool
    scanned_at: datetime

    class Config:
        from_attributes = True


class ScanStatusResponse(BaseModel):
    session_id: int
    folder_path: str
    status: str
    total_files: int
    processed_files: int
    failed_files: int
    progress_percent: float
    last_processed_file: Optional[str]
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]


class DuplicateGroupResponse(BaseModel):
    group_id: int
    files: List[MediaFileResponse]
    similarity_score: float
    status: str


class DuplicatesResponse(BaseModel):
    total_groups: int
    groups: List[DuplicateGroupResponse]


class OrganizePreviewItem(BaseModel):
    source_path: str
    destination_path: str
    date_taken: Optional[datetime]


class OrganizeResponse(BaseModel):
    success: bool
    message: str
    files_moved: int
    files_skipped: int
    preview: Optional[List[OrganizePreviewItem]] = None


class MediaQueryResponse(BaseModel):
    total_count: int
    files: List[MediaFileResponse]
    query: dict
