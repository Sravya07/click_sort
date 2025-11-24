# Photo Sorter API

A powerful REST API for organizing, deduplicating, and managing large photo collections (30,000+ images).

## Features

### Core Capabilities

- **High-Performance Scanning**: Efficiently scan folders with 30,000+ images
- **Resume Capability**: Interrupted scans automatically resume from where they left off
- **Incremental Scanning**: Only processes new or modified files on subsequent scans
- **Date-Based Queries**: Search photos by year, month, or specific date
- **Duplicate Detection**: Find similar images using perceptual hashing (handles crops, filters, resizes)
- **Auto-Organization**: Sort photos into `YEAR/Month` folder structure based on EXIF data
- **Favorites Management**: Mark favorites while keeping originals in their locations (using symlinks)

### Supported Formats

JPG, JPEG, PNG, GIF, BMP, TIFF, WebP, HEIC, HEIF

## Installation

### Prerequisites

- Python 3.9+
- pip

### Setup

1. Clone the repository:
```bash
git clone https://github.com/Sravya07/click_sort.git
cd click_sort
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the API server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### 1. Scanning (`/scan`)

#### Start/Resume a Scan
```http
POST /scan
Content-Type: application/json

{
    "folder_path": "/path/to/photos",
    "include_subfolders": true
}
```

**Response:**
```json
{
    "message": "Scan started for 30000 files",
    "session_id": 1,
    "status": "in_progress",
    "total_files": 30000
}
```

#### Check Scan Progress
```http
GET /scan/status/{session_id}
```

**Response:**
```json
{
    "session_id": 1,
    "folder_path": "/path/to/photos",
    "status": "in_progress",
    "total_files": 30000,
    "processed_files": 15000,
    "progress_percent": 50.0,
    "started_at": "2024-01-15T10:30:00"
}
```

### 2. Query by Date (`/media`)

#### Get Photos by Date
```http
# All photos from 2023
GET /media?year=2023

# All photos from June 2023
GET /media?year=2023&month=6

# Photos from a specific date
GET /media?year=2023&month=6&day=15
```

**Response:**
```json
{
    "total_count": 150,
    "files": [
        {
            "id": 1,
            "file_path": "/path/to/photo.jpg",
            "filename": "photo.jpg",
            "date_taken": "2023-06-15T14:30:00",
            "is_favorite": false
        }
    ],
    "query": {"year": 2023, "month": 6, "day": 15}
}
```

#### Get Available Years/Months
```http
GET /media/years
GET /media/months/2023
```

### 3. Duplicate Detection (`/duplicates`)

#### Find Duplicate Groups
```http
GET /duplicates?threshold=10&rescan=true
```

The `threshold` parameter controls sensitivity (1-30):
- Lower (5-10): Very similar images only
- Higher (15-20): More permissive, catches edited versions

**Response:**
```json
{
    "total_groups": 25,
    "groups": [
        {
            "group_id": 1,
            "files": [...],
            "similarity_score": 95.5,
            "status": "pending"
        }
    ]
}
```

#### Apply Action to Duplicates
```http
POST /duplicates/{group_id}/action
Content-Type: application/json

{
    "action": "delete",
    "file_ids": [2, 3, 4],
    "keep_file_id": 1
}
```

**Available Actions:**
- `keep`: Keep all files, mark as reviewed
- `delete`: Move files to `.trash` folder (except `keep_file_id`)
- `favorite`: Add to favorites folder (creates symlinks)
- `decide_later`: Skip for now

### 4. Organize Photos (`/organize`)

#### Preview Organization
```http
GET /organize/preview?folder_path=/path/to/photos
```

#### Organize by Date
```http
POST /organize
Content-Type: application/json

{
    "folder_path": "/path/to/photos",
    "dry_run": false
}
```

This creates the following structure:
```
photos/
├── 2023/
│   ├── 01-January/
│   ├── 02-February/
│   └── ...
├── 2024/
│   └── ...
└── favorites/  (symlinks to originals)
```

### 5. Statistics (`/stats`)

```http
GET /stats
```

**Response:**
```json
{
    "total_files": 30000,
    "total_favorites": 500,
    "organized_files": 25000,
    "pending_duplicate_groups": 25,
    "year_range": {"min": 2010, "max": 2024}
}
```

## Testing with Postman

### Setup Postman Collection

1. Open Postman
2. Create a new Collection named "Photo Sorter API"
3. Set a collection variable: `base_url` = `http://localhost:8000`

### Test Workflow

#### Step 1: Health Check
```
GET {{base_url}}/
```
Expected: `{"status": "healthy", "service": "Photo Sorter API"}`

#### Step 2: Start Scanning
```
POST {{base_url}}/scan
Body (JSON):
{
    "folder_path": "/Users/yourname/Pictures",
    "include_subfolders": true
}
```

#### Step 3: Monitor Progress
```
GET {{base_url}}/scan/status/1
```
Poll this endpoint until `status` is `"completed"`

#### Step 4: Query Photos
```
GET {{base_url}}/media?year=2023
GET {{base_url}}/media?year=2023&month=12
```

#### Step 5: Find Duplicates
```
GET {{base_url}}/duplicates?rescan=true&threshold=10
```

#### Step 6: Handle Duplicates
```
POST {{base_url}}/duplicates/1/action
Body (JSON):
{
    "action": "delete",
    "file_ids": [2, 3],
    "keep_file_id": 1
}
```

#### Step 7: Organize Photos
```
# Preview first
GET {{base_url}}/organize/preview?folder_path=/Users/yourname/Pictures

# Then organize
POST {{base_url}}/organize
Body (JSON):
{
    "folder_path": "/Users/yourname/Pictures",
    "dry_run": false
}
```

### Using cURL

```bash
# Health check
curl http://localhost:8000/

# Start scan
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/photos", "include_subfolders": true}'

# Check status
curl http://localhost:8000/scan/status/1

# Query by date
curl "http://localhost:8000/media?year=2023&month=6"

# Find duplicates
curl "http://localhost:8000/duplicates?rescan=true"

# Organize photos
curl -X POST http://localhost:8000/organize \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/photos", "dry_run": false}'
```

## Database

The application uses SQLite for tracking scanned files. The database file (`photo_sorter.db`) is created in the current directory.

To use a custom location:
```bash
export PHOTO_SORTER_DB=/path/to/custom/database.db
uvicorn app.main:app --reload
```

## Architecture

```
click_sort/
├── app/
│   ├── main.py           # FastAPI entry point
│   ├── database.py       # SQLAlchemy models
│   ├── models.py         # Pydantic schemas
│   ├── services/
│   │   ├── scanner.py    # Folder scanning with resume
│   │   ├── duplicates.py # Perceptual hash comparison
│   │   └── organizer.py  # EXIF-based organization
│   └── routers/
│       ├── scan.py       # Scanning endpoints
│       ├── media.py      # Date query endpoints
│       ├── duplicates.py # Duplicate management
│       └── organize.py   # Organization endpoints
├── data/                 # Database storage
├── tests/                # API tests
├── requirements.txt
└── README.md
```

## Performance Notes

- **Batch Processing**: Files are processed in batches of 100 for memory efficiency
- **Perceptual Hashing**: Uses pHash/dHash/aHash for fast similarity detection
- **Incremental Scans**: Skips unchanged files based on file size and modification time
- **Background Tasks**: Large folders (>100 files) are scanned in the background

## License

MIT License
