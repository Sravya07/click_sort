from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MediaQueryResponse, MediaFileResponse
from app.services.organizer import query_by_date

router = APIRouter(prefix="/media", tags=["Media"])


@router.get("", response_model=MediaQueryResponse)
async def get_media_by_date(
    year: Optional[int] = Query(None, ge=1900, le=2100, description="Year to filter by"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month to filter by (1-12)"),
    day: Optional[int] = Query(None, ge=1, le=31, description="Day to filter by (1-31)"),
    folder_path: Optional[str] = Query(None, description="Limit search to specific folder"),
    db: Session = Depends(get_db)
):
    """
    Query media files by date.

    Supports flexible date queries:
    - **Year only**: `/media?year=2023` - All photos from 2023
    - **Year + Month**: `/media?year=2023&month=6` - All photos from June 2023
    - **Specific date**: `/media?year=2023&month=6&day=15` - Photos from June 15, 2023

    Optionally limit to a specific folder path.
    """
    if month and not year:
        raise HTTPException(
            status_code=400,
            detail="Year is required when querying by month"
        )

    if day and (not year or not month):
        raise HTTPException(
            status_code=400,
            detail="Year and month are required when querying by day"
        )

    files = query_by_date(db, year=year, month=month, day=day, folder_path=folder_path)

    return MediaQueryResponse(
        total_count=len(files),
        files=[MediaFileResponse(**f) for f in files],
        query={
            'year': year,
            'month': month,
            'day': day,
            'folder_path': folder_path
        }
    )


@router.get("/years")
async def get_available_years(
    folder_path: Optional[str] = Query(None, description="Limit to specific folder"),
    db: Session = Depends(get_db)
):
    """Get list of years that have photos."""
    from sqlalchemy import distinct
    from app.database import MediaFile

    query = db.query(distinct(MediaFile.year)).filter(
        MediaFile.year.isnot(None),
        MediaFile.is_deleted == False
    )

    if folder_path:
        query = query.filter(MediaFile.folder_path.startswith(folder_path))

    years = [y[0] for y in query.order_by(MediaFile.year.desc()).all()]

    return {"years": years}


@router.get("/months/{year}")
async def get_available_months(
    year: int,
    folder_path: Optional[str] = Query(None, description="Limit to specific folder"),
    db: Session = Depends(get_db)
):
    """Get list of months that have photos for a given year."""
    from sqlalchemy import distinct, func
    from app.database import MediaFile

    query = db.query(
        MediaFile.month,
        func.count(MediaFile.id).label('count')
    ).filter(
        MediaFile.year == year,
        MediaFile.month.isnot(None),
        MediaFile.is_deleted == False
    )

    if folder_path:
        query = query.filter(MediaFile.folder_path.startswith(folder_path))

    results = query.group_by(MediaFile.month).order_by(MediaFile.month).all()

    months = [{'month': m, 'count': c} for m, c in results]

    return {"year": year, "months": months}
