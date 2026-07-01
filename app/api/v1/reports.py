"""Reports endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def reports_status() -> dict:
    return {"status": "ready", "message": "Report generation available after live trading"}
