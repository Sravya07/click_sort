from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.routers import media, duplicates, organize, scan


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(
    title="Photo Sorter API",
    description="""
## Photo Sorter API

A powerful API for organizing, deduplicating, and managing large photo collections.

### Features

- **Folder Scanning**: Scan folders with 30,000+ images efficiently with resume capability
- **Date-based Queries**: Query photos by year, month, or specific date
- **Duplicate Detection**: Find similar images using perceptual hashing (handles crops, filters, resizes)
- **Auto-Organization**: Sort photos into YEAR/Month folder structure based on EXIF data
- **Favorites Management**: Mark favorites while keeping originals in place

### Getting Started

1. **Scan a folder**: `POST /scan` with your folder path
2. **Check progress**: `GET /scan/status/{session_id}`
3. **Query by date**: `GET /media?year=2023&month=6`
4. **Find duplicates**: `GET /duplicates`
5. **Organize photos**: `POST /organize`
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(scan.router)
app.include_router(media.router)
app.include_router(duplicates.router)
app.include_router(organize.router)


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Photo Sorter API",
        "version": "1.0.0"
    }


@app.get("/stats", tags=["Stats"])
async def get_stats():
    """Get overall statistics about the photo library."""
    from sqlalchemy import func
    from app.database import SessionLocal, MediaFile, DuplicateGroup

    db = SessionLocal()
    try:
        total_files = db.query(func.count(MediaFile.id)).filter(
            MediaFile.is_deleted == False
        ).scalar()

        total_favorites = db.query(func.count(MediaFile.id)).filter(
            MediaFile.is_favorite == True,
            MediaFile.is_deleted == False
        ).scalar()

        organized_files = db.query(func.count(MediaFile.id)).filter(
            MediaFile.is_organized == True,
            MediaFile.is_deleted == False
        ).scalar()

        duplicate_groups = db.query(func.count(DuplicateGroup.id)).filter(
            DuplicateGroup.status == "pending"
        ).scalar()

        # Get year range
        min_year = db.query(func.min(MediaFile.year)).filter(
            MediaFile.year.isnot(None)
        ).scalar()

        max_year = db.query(func.max(MediaFile.year)).filter(
            MediaFile.year.isnot(None)
        ).scalar()

        return {
            "total_files": total_files or 0,
            "total_favorites": total_favorites or 0,
            "organized_files": organized_files or 0,
            "pending_duplicate_groups": duplicate_groups or 0,
            "year_range": {
                "min": min_year,
                "max": max_year
            }
        }
    finally:
        db.close()


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
