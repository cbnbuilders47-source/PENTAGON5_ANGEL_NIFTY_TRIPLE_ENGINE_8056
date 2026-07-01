"""Session scheduler status endpoint."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def scheduler_status(request: Request) -> dict:
    scheduler = request.app.state.session_scheduler
    status = scheduler.tick()
    request.app.state.app_state.apply_scheduler_status(status)
    return {
        "current_phase": status.current_phase.value,
        "bias_locked": status.bias_locked,
        "new_entries_allowed": status.new_entries_allowed,
        "force_exit_active": status.force_exit_active,
        "shutdown_prep": status.shutdown_prep,
        "events": status.events_today,
    }
