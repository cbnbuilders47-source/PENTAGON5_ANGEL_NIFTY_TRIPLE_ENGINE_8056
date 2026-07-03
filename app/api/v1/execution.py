"""Execution API endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.models.enums import ExitReason

router = APIRouter()


class ManualAction(BaseModel):
    approval_id: str


@router.get("/status")
async def execution_status(request: Request) -> dict:
    return request.app.state.execution_controller.status()


@router.post("/manual/approve")
async def manual_approve(request: Request, body: ManualAction) -> dict:
    result = await request.app.state.execution_controller.approve_manual(body.approval_id)
    return result.to_dict()


@router.post("/manual/reject")
async def manual_reject(request: Request, body: ManualAction) -> dict:
    result = await request.app.state.execution_controller.reject_manual(body.approval_id)
    return result.to_dict()


@router.post("/exit-all")
async def exit_all(request: Request) -> dict:
    results = await request.app.state.execution_controller.exit_all(ExitReason.FORCE_EXIT)
    return {"results": [r.to_dict() for r in results]}
