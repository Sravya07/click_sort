"""Tests for the Photo Sorter API."""
import os
import shutil
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.database import Base, engine, SessionLocal, MediaFile, init_db


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh test database for each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def temp_folder():
    """Create a temporary folder with test images."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_folder_with_images(temp_folder):
    """Create a temporary folder with sample images."""
    # Create different colored images
    for i, color in enumerate(['red', 'green', 'blue']):
        img = Image.new('RGB', (100, 100), color=color)
        img.save(os.path.join(temp_folder, f'image_{i}.jpg'))
    return temp_folder


@pytest.fixture
def temp_folder_with_similar_images(temp_folder):
    """Create a temporary folder with similar (duplicate) images."""
    # Create an image with a pattern
    img = Image.new('RGB', (200, 200), color='white')
    pixels = img.load()
    for i in range(0, 200, 20):
        for j in range(0, 200, 20):
            for di in range(10):
                for dj in range(10):
                    if i + di < 200 and j + dj < 200:
                        pixels[i + di, j + dj] = (0, 0, 0)

    img.save(os.path.join(temp_folder, 'original.jpg'))
    img.save(os.path.join(temp_folder, 'duplicate.jpg'))

    # Create a different image
    img2 = Image.new('RGB', (100, 100), color='red')
    img2.save(os.path.join(temp_folder, 'different.jpg'))

    return temp_folder


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        """Test that health check returns healthy status."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Photo Sorter API"


class TestScanEndpoints:
    """Tests for scanning endpoints."""

    def test_scan_nonexistent_folder(self, client):
        """Test scanning a folder that doesn't exist."""
        response = client.post("/scan", json={
            "folder_path": "/nonexistent/folder",
            "include_subfolders": True
        })
        assert response.status_code == 400

    def test_scan_empty_folder(self, client, temp_folder):
        """Test scanning an empty folder."""
        response = client.post("/scan", json={
            "folder_path": temp_folder,
            "include_subfolders": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0

    def test_scan_folder_with_images(self, client, temp_folder_with_images):
        """Test scanning a folder with images."""
        response = client.post("/scan", json={
            "folder_path": temp_folder_with_images,
            "include_subfolders": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 3
        assert data["status"] == "completed"

    def test_list_scan_sessions(self, client, temp_folder_with_images):
        """Test listing scan sessions."""
        # First do a scan
        client.post("/scan", json={
            "folder_path": temp_folder_with_images,
            "include_subfolders": True
        })

        response = client.get("/scan/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) >= 1


class TestMediaEndpoints:
    """Tests for media query endpoints."""

    def test_query_with_no_results(self, client, test_db):
        """Test querying when no files have been scanned."""
        response = client.get("/media?year=2023")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0

    def test_query_requires_year_for_month(self, client):
        """Test that month query requires year."""
        response = client.get("/media?month=6")
        assert response.status_code == 400

    def test_query_requires_year_month_for_day(self, client):
        """Test that day query requires year and month."""
        response = client.get("/media?day=15")
        assert response.status_code == 400

    def test_get_available_years(self, client, test_db):
        """Test getting available years."""
        response = client.get("/media/years")
        assert response.status_code == 200
        assert "years" in response.json()

    def test_get_months_for_year(self, client, test_db):
        """Test getting months for a year."""
        response = client.get("/media/months/2023")
        assert response.status_code == 200
        data = response.json()
        assert data["year"] == 2023
        assert "months" in data


class TestDuplicateEndpoints:
    """Tests for duplicate detection endpoints."""

    def test_get_duplicates_empty(self, client, test_db):
        """Test getting duplicates when none exist."""
        response = client.get("/duplicates")
        assert response.status_code == 200
        data = response.json()
        assert data["total_groups"] == 0

    def test_scan_for_duplicates(self, client, temp_folder_with_similar_images, test_db):
        """Test scanning for duplicates."""
        # First scan the folder
        client.post("/scan", json={
            "folder_path": temp_folder_with_similar_images,
            "include_subfolders": True
        })

        # Then find duplicates
        response = client.get("/duplicates?rescan=true")
        assert response.status_code == 200

    def test_get_nonexistent_group(self, client, test_db):
        """Test getting a duplicate group that doesn't exist."""
        response = client.get("/duplicates/999")
        assert response.status_code == 404


class TestOrganizeEndpoints:
    """Tests for organization endpoints."""

    def test_organize_nonexistent_folder(self, client):
        """Test organizing a folder that doesn't exist."""
        response = client.post("/organize", json={
            "folder_path": "/nonexistent/folder",
            "dry_run": False
        })
        assert response.status_code == 400

    def test_organize_preview(self, client, temp_folder_with_images, test_db):
        """Test preview organization."""
        # First scan
        client.post("/scan", json={
            "folder_path": temp_folder_with_images,
            "include_subfolders": True
        })

        # Then preview
        response = client.get(f"/organize/preview?folder_path={temp_folder_with_images}")
        assert response.status_code == 200

    def test_organize_dry_run(self, client, temp_folder_with_images, test_db):
        """Test organize with dry run."""
        # First scan
        client.post("/scan", json={
            "folder_path": temp_folder_with_images,
            "include_subfolders": True
        })

        # Organize with dry run
        response = client.post("/organize", json={
            "folder_path": temp_folder_with_images,
            "dry_run": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["files_moved"] == 0  # Dry run shouldn't move files


class TestStatsEndpoint:
    """Tests for the stats endpoint."""

    def test_stats_empty(self, client, test_db):
        """Test stats when no files have been scanned."""
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0

    def test_stats_after_scan(self, client, temp_folder_with_images, test_db):
        """Test stats after scanning files."""
        # First scan
        client.post("/scan", json={
            "folder_path": temp_folder_with_images,
            "include_subfolders": True
        })

        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 3


class TestScannerService:
    """Tests for the scanner service."""

    def test_get_file_hash(self, temp_folder):
        """Test file hash calculation."""
        from app.services.scanner import get_file_hash

        # Create a test file
        img = Image.new('RGB', (100, 100), color='red')
        path = os.path.join(temp_folder, 'test.jpg')
        img.save(path)

        hash1 = get_file_hash(path)
        hash2 = get_file_hash(path)

        assert hash1 == hash2  # Same file should have same hash
        assert len(hash1) == 32  # MD5 hash length

    def test_get_perceptual_hashes(self, temp_folder):
        """Test perceptual hash calculation."""
        from app.services.scanner import get_perceptual_hashes

        img = Image.new('RGB', (100, 100), color='red')
        path = os.path.join(temp_folder, 'test.jpg')
        img.save(path)

        phash, dhash, ahash = get_perceptual_hashes(path)

        assert phash is not None
        assert dhash is not None
        assert ahash is not None

    def test_get_file_date(self, temp_folder):
        """Test file date extraction."""
        from app.services.scanner import get_file_date

        img = Image.new('RGB', (100, 100), color='red')
        path = os.path.join(temp_folder, 'test.jpg')
        img.save(path)

        date = get_file_date(path)

        assert isinstance(date, datetime)
        # Should be close to now
        assert (datetime.now() - date).total_seconds() < 60

    def test_discover_files(self, temp_folder_with_images):
        """Test file discovery."""
        from app.services.scanner import discover_files

        files = list(discover_files(temp_folder_with_images))
        assert len(files) == 3

    def test_discover_files_excludes_non_images(self, temp_folder):
        """Test that non-image files are excluded."""
        from app.services.scanner import discover_files

        # Create a text file
        with open(os.path.join(temp_folder, 'readme.txt'), 'w') as f:
            f.write('test')

        # Create an image
        img = Image.new('RGB', (100, 100), color='red')
        img.save(os.path.join(temp_folder, 'image.jpg'))

        files = list(discover_files(temp_folder))
        assert len(files) == 1

    def test_discover_files_excludes_videos(self, temp_folder):
        """Test that video files are excluded from scanning."""
        from app.services.scanner import discover_files

        # Create fake video files (just empty files with video extensions)
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm']
        for ext in video_extensions:
            with open(os.path.join(temp_folder, f'video{ext}'), 'wb') as f:
                f.write(b'\x00' * 100)  # Write some dummy bytes

        # Create an image
        img = Image.new('RGB', (100, 100), color='red')
        img.save(os.path.join(temp_folder, 'image.jpg'))

        files = list(discover_files(temp_folder))
        assert len(files) == 1
        assert files[0].endswith('image.jpg')

    def test_discover_files_excludes_audio(self, temp_folder):
        """Test that audio files are excluded from scanning."""
        from app.services.scanner import discover_files

        # Create fake audio files
        audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.m4a']
        for ext in audio_extensions:
            with open(os.path.join(temp_folder, f'audio{ext}'), 'wb') as f:
                f.write(b'\x00' * 100)

        # Create an image
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(os.path.join(temp_folder, 'photo.png'))

        files = list(discover_files(temp_folder))
        assert len(files) == 1
        assert files[0].endswith('photo.png')

    def test_is_valid_image(self, temp_folder):
        """Test that is_valid_image correctly identifies valid images."""
        from app.services.scanner import is_valid_image

        # Create a valid image
        img = Image.new('RGB', (100, 100), color='red')
        valid_path = os.path.join(temp_folder, 'valid.jpg')
        img.save(valid_path)

        # Create an invalid file with image extension
        invalid_path = os.path.join(temp_folder, 'invalid.jpg')
        with open(invalid_path, 'wb') as f:
            f.write(b'not an image content')

        assert is_valid_image(valid_path) is True
        assert is_valid_image(invalid_path) is False


class TestDuplicatesService:
    """Tests for the duplicates service."""

    def test_hamming_distance_identical(self):
        """Test hamming distance for identical hashes."""
        from app.services.duplicates import hamming_distance

        distance = hamming_distance("0000000000000000", "0000000000000000")
        assert distance == 0

    def test_hamming_distance_different(self):
        """Test hamming distance for different hashes."""
        from app.services.duplicates import hamming_distance

        # These hashes are different
        distance = hamming_distance("0000000000000000", "ffffffffffffffff")
        assert distance > 0

    def test_hamming_distance_none_hash(self):
        """Test hamming distance with None hash."""
        from app.services.duplicates import hamming_distance

        distance = hamming_distance(None, "0000000000000000")
        assert distance == 64  # Maximum distance


class TestOrganizerService:
    """Tests for the organizer service."""

    def test_get_destination_path(self):
        """Test destination path generation."""
        from app.services.organizer import get_destination_path

        date = datetime(2023, 6, 15, 14, 30, 0)
        dest = get_destination_path("/photos", date, "image.jpg")

        assert "/photos/2023/06-June/image.jpg" == dest

    def test_month_names(self):
        """Test that all months have correct names."""
        from app.services.organizer import MONTH_NAMES

        assert len(MONTH_NAMES) == 12
        assert MONTH_NAMES[1] == "01-January"
        assert MONTH_NAMES[12] == "12-December"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
