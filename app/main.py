"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.router import api_router
from app.broker.angel_manager import AngelManager
from app.broker.margin_manager import MarginManager
from app.broker.order_manager import OrderManager
from app.broker.position_manager import PositionManager
from app.broker.rate_limit import RateLimitTracker
from app.broker.readiness import BrokerReadinessGate
from app.broker.session_service import BrokerSessionService
from app.broker.token_manager import TokenManager
from app.broker.websocket_manager import WebSocketManager
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.shutdown_manager import ShutdownManager
from app.core.startup_validator import validate_startup
from app.core.state import get_app_state
from app.execution.execution_controller import ExecutionController
from app.execution.recovery import ExecutionRecovery
from app.risk.exit_monitor import ExitMonitor
from app.engines.adaptive_controller import AdaptiveController
from app.engines.runtime import intelligence_loop
from app.market.atm_manager import ATMManager
from app.market.candle_builder import CandleBuilder
from app.market.instrument_master import InstrumentMaster
from app.risk.force_exit import ForceExitManager
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
from app.scheduler.runtime import scheduler_loop
from app.scheduler.session_scheduler import SessionScheduler
from app.storage.db import init_db

PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)

    init_db()

    validation = validate_startup()
    if not validation.valid:
        for check in validation.checks:
            if not check.passed:
                logger.warning("Startup check failed: %s — %s", check.name, check.message)

    app_state = get_app_state()
    token_manager = TokenManager()
    angel_manager = AngelManager(settings, token_manager)
    websocket_manager = WebSocketManager()
    instrument_master = InstrumentMaster(settings)
    atm_manager = ATMManager(instrument_master)
    candle_builder = CandleBuilder()
    rate_limiter = RateLimitTracker()
    session_scheduler = SessionScheduler()
    trading_locks = TradingLocks()

    readiness_gate = BrokerReadinessGate(
        state=app_state,
        angel_manager=angel_manager,
        token_manager=token_manager,
        websocket_manager=websocket_manager,
        instrument_master=instrument_master,
        atm_manager=atm_manager,
        candle_builder=candle_builder,
        rate_limiter=rate_limiter,
    )

    risk_manager = RiskManager(
        state=app_state,
        locks=trading_locks,
        scheduler=session_scheduler,
        readiness_gate=readiness_gate,
    )
    force_exit_manager = ForceExitManager(app_state)
    order_manager = OrderManager(angel_manager, rate_limiter)
    position_manager = PositionManager(angel_manager, rate_limiter)
    execution_controller = ExecutionController(
        state=app_state,
        risk_manager=risk_manager,
        locks=trading_locks,
        scheduler=session_scheduler,
        readiness_gate=readiness_gate,
        order_manager=order_manager,
        position_manager=position_manager,
    )
    execution_recovery = ExecutionRecovery(app_state, order_manager, position_manager)
    exit_monitor = ExitMonitor(app_state, execution_controller, session_scheduler)

    app.state.settings = settings
    app.state.app_state = app_state
    app.state.candle_builder = candle_builder
    app.state.angel_manager = angel_manager
    app.state.token_manager = token_manager
    app.state.websocket_manager = websocket_manager
    app.state.margin_manager = MarginManager(app_state, angel_manager)
    app.state.instrument_master = instrument_master
    app.state.atm_manager = atm_manager
    app.state.rate_limiter = rate_limiter
    app.state.session_scheduler = session_scheduler
    app.state.readiness_gate = readiness_gate
    app.state.adaptive_controller = AdaptiveController(app_state, candle_builder)
    app.state.risk_manager = risk_manager
    app.state.trading_locks = trading_locks
    app.state.force_exit_manager = force_exit_manager
    app.state.order_manager = order_manager
    app.state.position_manager = position_manager
    app.state.execution_controller = execution_controller
    app.state.execution_recovery = execution_recovery
    app.state.exit_monitor = exit_monitor
    app.state.shutdown_manager = ShutdownManager(app)
    app.state.broker_session = BrokerSessionService(
        settings=settings,
        state=app_state,
        angel_manager=angel_manager,
        token_manager=token_manager,
        margin_manager=app.state.margin_manager,
        websocket_manager=websocket_manager,
        instrument_master=instrument_master,
        atm_manager=atm_manager,
        candle_builder=candle_builder,
    )

    logger.info("%s v%s starting on port %s", settings.app_name, settings.app_version, settings.port)
    intel_task = asyncio.create_task(intelligence_loop(app))
    sched_task = asyncio.create_task(scheduler_loop(app))
    yield
    for task in (intel_task, sched_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await app.state.broker_session.disconnect()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")

    templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")
    app.state.templates = templates

    app.include_router(api_router)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"app_name": settings.app_name},
        )

    return app


app = create_app()
