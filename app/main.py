"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.router import api_router
from app.broker.angel_manager import AngelManager
from app.broker.margin_manager import MarginManager
from app.broker.token_manager import TokenManager
from app.broker.websocket_manager import WebSocketManager
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.state import get_app_state
from app.engines.adaptive_controller import AdaptiveController
from app.market.candle_builder import CandleBuilder
from app.market.instrument_master import InstrumentMaster
from app.risk.locks import TradingLocks
from app.risk.risk_manager import RiskManager
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

    app.state.settings = settings
    app.state.app_state = get_app_state()
    app.state.candle_builder = CandleBuilder()
    app.state.angel_manager = AngelManager(settings)
    app.state.token_manager = TokenManager()
    app.state.websocket_manager = WebSocketManager()
    app.state.margin_manager = MarginManager(app.state.app_state)
    app.state.instrument_master = InstrumentMaster()
    app.state.adaptive_controller = AdaptiveController(app.state.app_state)
    app.state.risk_manager = RiskManager(app.state.app_state)
    app.state.trading_locks = TradingLocks()

    logger.info("%s v%s starting on port %s", settings.app_name, settings.app_version, settings.port)
    yield
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
