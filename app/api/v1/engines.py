"""Engine status and allocation endpoints."""

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import AllocationResponse, AllocationUpdate, EngineInfo

router = APIRouter()


@router.get("/status")
async def engines_status(request: Request) -> list[EngineInfo]:
    state = request.app.state.app_state
    return [
        EngineInfo(
            name=e.name,
            status=e.status,
            allocation_pct=e.allocation_pct,
            allocated_margin=e.allocated_margin,
            pnl=e.pnl,
            open_positions=e.open_positions,
        )
        for e in state.engines.values()
    ]


@router.get("/allocations", response_model=AllocationResponse)
async def get_allocations(request: Request) -> AllocationResponse:
    state = request.app.state.app_state
    alloc = state.allocations
    return AllocationResponse(
        normal=alloc.get("normal", 0),
        wick=alloc.get("wick", 0),
        ultra=alloc.get("ultra", 0),
    )


@router.put("/allocations", response_model=AllocationResponse)
async def update_allocations(
    request: Request,
    body: AllocationUpdate,
) -> AllocationResponse:
    state = request.app.state.app_state
    try:
        state.update_allocations(body.normal, body.wick, body.ultra)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AllocationResponse(
        normal=body.normal,
        wick=body.wick,
        ultra=body.ultra,
    )
