"""System control endpoints."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/restart")
async def system_restart(request: Request) -> dict:
    recovery = request.app.state.execution_recovery
    summary = await recovery.recover()
    return {"status": "restarted", "recovery": summary}


@router.post("/shutdown")
async def system_shutdown(request: Request) -> dict:
    await request.app.state.shutdown_manager.shutdown()
    return {"status": "shutdown_initiated"}
