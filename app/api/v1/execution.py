"""Execution API endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.trade_password import require_trade_password
from app.models.enums import ExitReason

router = APIRouter()


class ManualAction(BaseModel):
    approval_id: str
    password: str | None = None


class PasswordBody(BaseModel):
    password: str | None = None


@router.get("/status")
async def execution_status(request: Request) -> dict:
    return request.app.state.execution_controller.status()


@router.post("/manual/approve")
async def manual_approve(request: Request, body: ManualAction) -> dict:
    require_trade_password(request, body.password, "manual_approve")
    result = await request.app.state.execution_controller.approve_manual(body.approval_id)
    return result.to_dict()


@router.post("/manual/reject")
async def manual_reject(request: Request, body: ManualAction) -> dict:
    result = await request.app.state.execution_controller.reject_manual(body.approval_id)
    return result.to_dict()


@router.post("/exit-all")
async def exit_all(request: Request, body: PasswordBody) -> dict:
    require_trade_password(request, body.password, "exit_all")
    results = await request.app.state.execution_controller.exit_all(ExitReason.FORCE_EXIT)
    return {"results": [r.to_dict() for r in results]}
