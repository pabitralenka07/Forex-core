"""FastAPI Application entrypoint with Request ID middleware and global error handling."""

import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.auth import router as auth_router
from app.api.v1.convert import router as convert_router
from app.api.v1.currencies import router as currencies_router
from app.api.v1.favorites import router as favorites_router
from app.api.v1.health import router as health_router
from app.api.v1.historical import router as historical_router
from app.api.v1.history import router as history_router
from app.api.v1.rates import router as rates_router
from app.config import get_settings
from app.core.exceptions import CurrencyConverterException
from app.core.logging import request_id_ctx, setup_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.security_headers import SecurityHeadersMiddleware
from app.database.session import init_db
from app.schemas.envelope import APIResponse
from app.services.scheduler import get_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown routines."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(
        "Starting %s v%s in %s mode",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )

    # Initialize database tables
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as db_err:
        logger.error("Failed to initialize database: %s", db_err)

    # Start background rate refresh scheduler
    scheduler = get_scheduler()
    scheduler.start()

    yield

    logger.info("Shutting down %s", settings.app_name)
    await scheduler.stop()


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Portfolio-quality financial currency converter API.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Rate limiting state
    app.state.limiter = limiter

    # Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request-ID Correlation Middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        req_id = request.headers.get("X-Request-ID")
        if not req_id or not req_id.strip():
            req_id = uuid.uuid4().hex

        request.state.request_id = req_id
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)

    # Global Exception Handlers conforming to Section 8 envelope
    @app.exception_handler(CurrencyConverterException)
    async def currency_converter_exception_handler(
        request: Request, exc: CurrencyConverterException
    ) -> JSONResponse:
        req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)
        error_response = APIResponse.create_error(
            code=exc.code,
            message=exc.message,
            request_id=req_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return rate_limit_exceeded_handler(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)
        code = "HTTP_ERROR"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "NOT_FOUND"
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "UNAUTHORIZED"
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            code = "RATE_LIMIT_EXCEEDED"

        error_response = APIResponse.create_error(
            code=code,
            message=str(exc.detail),
            request_id=req_id,
        )
        headers = getattr(exc, "headers", None) or {}
        headers["X-Request-ID"] = req_id
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)
        error_response = APIResponse.create_error(
            code="VALIDATION_ERROR",
            message=f"Request validation failed: {exc.errors()}",
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response.model_dump(),
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)
        logger.exception("Unhandled server exception: %s", exc)
        error_response = APIResponse.create_error(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
            request_id=req_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(),
            headers={"X-Request-ID": req_id},
        )

    # Register Routers
    # Root-level health & readiness per section 8 spec
    app.include_router(health_router)
    # Also mount under API v1 prefix
    app.include_router(health_router, prefix=settings.api_v1_prefix)
    app.include_router(convert_router, prefix=settings.api_v1_prefix)
    app.include_router(rates_router, prefix=settings.api_v1_prefix)
    app.include_router(currencies_router, prefix=settings.api_v1_prefix)
    app.include_router(historical_router, prefix=settings.api_v1_prefix)
    app.include_router(history_router, prefix=settings.api_v1_prefix)
    app.include_router(favorites_router, prefix=settings.api_v1_prefix)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)

    return app


app = create_application()
