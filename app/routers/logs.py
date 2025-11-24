from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.services.logger import get_recent_logs, get_session_logs, LOGS_DIR

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("")
async def get_logs(
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines to return"),
    session_id: Optional[int] = Query(None, description="Filter by session ID")
):
    """
    Get recent log entries.

    - **lines**: Number of recent lines to return (default 100, max 1000)
    - **session_id**: Optional session ID to filter logs for a specific scan session
    """
    if session_id:
        log_lines = get_session_logs(session_id, lines)
    else:
        log_lines = get_recent_logs(lines)

    return {
        "total_lines": len(log_lines),
        "logs": [line.strip() for line in log_lines]
    }


@router.get("/raw", response_class=PlainTextResponse)
async def get_logs_raw(
    lines: int = Query(100, ge=1, le=1000),
    session_id: Optional[int] = Query(None)
):
    """Get logs as plain text (useful for viewing in terminal)."""
    if session_id:
        log_lines = get_session_logs(session_id, lines)
    else:
        log_lines = get_recent_logs(lines)

    return "".join(log_lines)


@router.get("/files")
async def list_log_files():
    """List all available log files."""
    log_files = sorted(LOGS_DIR.glob("*.log"), reverse=True)

    return {
        "log_directory": str(LOGS_DIR),
        "files": [
            {
                "name": f.name,
                "size_bytes": f.stat().st_size,
                "modified": f.stat().st_mtime
            }
            for f in log_files
        ]
    }
