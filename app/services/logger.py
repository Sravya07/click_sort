import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Configure logging format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SessionLogger:
    """Logger for tracking scan session activities."""

    def __init__(self, session_id: Optional[int] = None):
        self.session_id = session_id
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up logger with file and console handlers."""
        logger_name = f"session_{self.session_id}" if self.session_id else "photo_sorter"
        logger = logging.getLogger(logger_name)

        # Avoid duplicate handlers
        if logger.handlers:
            return logger

        logger.setLevel(logging.DEBUG)

        # File handler - daily log file
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = LOGS_DIR / f"photo_sorter_{today}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        logger.addHandler(console_handler)

        return logger

    def _format_message(self, message: str) -> str:
        """Format message with session ID if available."""
        if self.session_id:
            return f"[Session {self.session_id}] {message}"
        return message

    def info(self, message: str):
        """Log info message."""
        self.logger.info(self._format_message(message))

    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(self._format_message(message))

    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(self._format_message(message))

    def error(self, message: str):
        """Log error message."""
        self.logger.error(self._format_message(message))

    def scan_started(self, folder_path: str, total_files: int):
        """Log scan start."""
        self.info(f"SCAN STARTED - Folder: {folder_path}, Total files: {total_files}")

    def scan_progress(self, processed: int, total: int, current_file: str = ""):
        """Log scan progress."""
        percent = (processed / total * 100) if total > 0 else 0
        msg = f"PROGRESS: {processed}/{total} ({percent:.1f}%)"
        if current_file:
            msg += f" - {os.path.basename(current_file)}"
        self.debug(msg)

    def scan_completed(self, processed: int, failed: int, new_files: int, skipped: int):
        """Log scan completion."""
        self.info(f"SCAN COMPLETED - Processed: {processed}, New: {new_files}, Skipped: {skipped}, Failed: {failed}")

    def scan_failed(self, error: str):
        """Log scan failure."""
        self.error(f"SCAN FAILED - {error}")

    def scan_interrupted(self):
        """Log scan interruption."""
        self.warning("SCAN INTERRUPTED - Server stopped during scan")

    def scan_resumed(self, from_file: str):
        """Log scan resume."""
        self.info(f"SCAN RESUMED - From: {from_file}")

    def scan_cancelled(self):
        """Log scan cancellation."""
        self.warning("SCAN CANCELLED - User cancelled the scan")

    def file_processed(self, file_path: str, date_taken: Optional[datetime] = None):
        """Log file processing."""
        date_str = date_taken.strftime("%Y-%m-%d") if date_taken else "no date"
        self.debug(f"Processed: {os.path.basename(file_path)} ({date_str})")

    def file_skipped(self, file_path: str, reason: str = "already scanned"):
        """Log file skip."""
        self.debug(f"Skipped: {os.path.basename(file_path)} - {reason}")

    def file_failed(self, file_path: str, error: str):
        """Log file processing failure."""
        self.warning(f"Failed: {os.path.basename(file_path)} - {error}")

    def duplicate_found(self, group_id: int, file_count: int):
        """Log duplicate detection."""
        self.info(f"DUPLICATE GROUP {group_id} - {file_count} similar files found")

    def organize_started(self, folder_path: str):
        """Log organize start."""
        self.info(f"ORGANIZE STARTED - Folder: {folder_path}")

    def organize_completed(self, moved: int, skipped: int):
        """Log organize completion."""
        self.info(f"ORGANIZE COMPLETED - Moved: {moved}, Skipped: {skipped}")

    def file_moved(self, source: str, destination: str):
        """Log file move."""
        self.debug(f"Moved: {os.path.basename(source)} -> {destination}")


# Global logger instance for general logging
app_logger = SessionLogger()


def get_session_logger(session_id: int) -> SessionLogger:
    """Get a logger for a specific session."""
    return SessionLogger(session_id)


def get_recent_logs(lines: int = 100) -> list:
    """Get recent log entries."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"photo_sorter_{today}.log"

    if not log_file.exists():
        return []

    with open(log_file, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
        return all_lines[-lines:]


def get_session_logs(session_id: int, lines: int = 100) -> list:
    """Get log entries for a specific session."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"photo_sorter_{today}.log"

    if not log_file.exists():
        return []

    session_marker = f"[Session {session_id}]"
    with open(log_file, 'r', encoding='utf-8') as f:
        session_lines = [line for line in f.readlines() if session_marker in line]
        return session_lines[-lines:]
