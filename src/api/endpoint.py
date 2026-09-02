
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from config.settings import API_VERSION, CAMERAS
from core.production.events import ProductionEvent
from database.repository import EventRepository, StatusRepository

from .dependencies import get_event_repository, get_status_repository
from .schemas import (
    API_V1_PREFIX,
    ApiResponse,
    CameraInfoSchema,
    CameraStatusSchema,
    ErrorDetail,
    EventListResponse,
    HealthResponse,
    ProductionEventSchema,
    ReportSummarySchema,
    SystemStatusSchema,
)

logger = logging.getLogger("api")

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

VALID_PERIODS = ("today", "week", "month", "all")

_TAGS = [
    {"name": "health", "description": "Liveness and service metadata."},
    {"name": "cameras", "description": "Configured cameras (no secrets exposed)."},
    {"name": "status", "description": "Runtime camera/system heartbeat status."},
    {"name": "events", "description": "Production events (read and write)."},
    {"name": "reports", "description": "Aggregate production metrics."},
]


class ApiError(Exception):
    """Domain-level error translated to a consistent JSON response."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _envelope(
    data: object | None = None,
    *,
    success: bool = True,
    error: ErrorDetail | None = None,
) -> dict:
    """Build the standard response envelope."""
    return ApiResponse(success=success, data=data, error=error).model_dump()


def _event_to_schema(event: ProductionEvent) -> ProductionEventSchema:
    """Convert a domain event into its API schema (no duplicate logic)."""
    return ProductionEventSchema(
        timestamp=event.timestamp,
        line_id=event.line_id,
        camera_id=event.camera_id,
        detection_id=event.detection_id,
        direction=event.direction if event.direction in ("UP", "DOWN") else "DOWN",
        bag_no=event.bag_no,
        shift=event.shift,
        production_batch=event.production_batch,
    )


def _parse_event_timestamp(value: str) -> datetime | None:
    """Best-effort ISO-8601 parse; returns None when unparseable."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _filter_events(
    events: list[ProductionEvent],
    line_id: str | None,
    camera_id: str | None,
    direction: str | None,
    shift: str | None,
) -> list[ProductionEvent]:
    """Apply optional equality filters to events (newest first)."""
    filtered = [
        e for e in events
        if (line_id is None or e.line_id == line_id)
        and (camera_id is None or e.camera_id == camera_id)
        and (direction is None or e.direction == direction)
        and (shift is None or e.shift == shift)
    ]
    filtered.sort(key=lambda e: e.timestamp, reverse=True)
    return filtered


app = FastAPI(
    title="Bag Detection System API",
    description=(
        "REST API for the cement-bag detection / production-monitoring "
        "pipeline. Provides production events, live camera status, and "
        "report aggregates. Same backing store as the detection app and "
        "Streamlit dashboard."
    ),
    version=API_VERSION,
    openapi_tags=_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Declare stable operation IDs so OpenAPI clients generate clean names.
for _route in app.router.routes:
    if isinstance(_route, APIRoute):
        _route.operation_id = _route.operation_id or _route.name


# ============================================================
# Exception handlers (consistent error envelope)
# ============================================================

@app.exception_handler(ApiError)
async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    logger.warning("API error %s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            success=False,
            error=ErrorDetail(code=exc.code, message=exc.message),
        ),
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(
            success=False,
            error=ErrorDetail(code="HTTP_ERROR", message=str(exc.detail)),
        ),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("Request validation failed: %s", exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            success=False,
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request data failed validation.",
            ),
        ),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            success=False,
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred.",
            ),
        ),
    )


# ============================================================
# Request / response logging middleware
# ============================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request and response with outcome-based severity."""
    started = time.perf_counter()
    client = request.client.host if request.client else "-"

    logger.debug(
        "REQUEST %s %s from %s", request.method, request.url.path, client
    )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "ERROR %s %s crashed after %.1f ms",
            request.method,
            request.url.path,
            (time.perf_counter() - started) * 1000,
        )
        raise

    duration_ms = (time.perf_counter() - started) * 1000

    if response.status_code >= 500:
        logger.error(
            "RESPONSE %s %s -> %d (%.1f ms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    elif response.status_code >= 400:
        logger.warning(
            "RESPONSE %s %s -> %d (%.1f ms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    else:
        logger.info(
            "RESPONSE %s %s -> %d (%.1f ms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )

    return response




# ============================================================
# Health
# ============================================================

@app.get(
    f"{API_V1_PREFIX}/health",
    tags=["health"],
    response_model=ApiResponse[HealthResponse],
    summary="Liveness probe.",
)
def read_health() -> dict:
    return _envelope(
        HealthResponse(
            status="ok",
            version=API_VERSION,
            time=datetime.now().isoformat(timespec="seconds"),
        )
    )


# ============================================================
# Cameras
# ============================================================

@app.get(
    f"{API_V1_PREFIX}/cameras",
    tags=["cameras"],
    response_model=ApiResponse[list[CameraInfoSchema]],
    summary="List configured cameras (secrets stripped).",
)
def list_cameras() -> dict:
    cameras = [
        CameraInfoSchema(
            camera_id=c["camera_id"],
            line_id=c["line_id"],
            enabled=bool(c.get("enabled", True)),
        )
        for c in CAMERAS
    ]
    return _envelope(cameras)


# ============================================================
# Status
# ============================================================

@app.get(
    f"{API_V1_PREFIX}/status",
    tags=["status"],
    response_model=ApiResponse[SystemStatusSchema],
    summary="Full system status (all cameras + summary).",
)
def read_status(
    status_repo: Annotated[StatusRepository, Depends(get_status_repository)],
) -> dict:
    return _envelope(SystemStatusSchema(**status_repo.read_status()))


@app.get(
    f"{API_V1_PREFIX}/status/cameras/{{camera_id}}",
    tags=["status"],
    response_model=ApiResponse[CameraStatusSchema],
    summary="Status of a single camera.",
    responses={404: {"description": "Camera not found in status store."}},
)
def read_camera_status(
    camera_id: str,
    status_repo: Annotated[StatusRepository, Depends(get_status_repository)],
) -> dict:
    payload = status_repo.read_status()
    camera = payload.get("cameras", {}).get(camera_id)

    if camera is None:
        raise ApiError("NOT_FOUND", f"Camera {camera_id!r} not found.", 404)

    return _envelope(CameraStatusSchema(**camera))



# ============================================================
# Production events
# ============================================================

@app.get(
    f"{API_V1_PREFIX}/events",
    tags=["events"],
    response_model=ApiResponse[EventListResponse],
    summary="List production events with optional filters and pagination.",
)
def list_events(
    event_repo: Annotated[EventRepository, Depends(get_event_repository)],
    line_id: str | None = None,
    camera_id: str | None = None,
    direction: str | None = None,
    shift: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    if not 1 <= limit <= MAX_LIMIT:
        raise ApiError(
            "INVALID_LIMIT",
            f"limit must be between 1 and {MAX_LIMIT}.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if offset < 0:
        raise ApiError(
            "INVALID_OFFSET",
            "offset must be >= 0.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    events = _filter_events(
        event_repo.read_events(as_dataframe=False),
        line_id=line_id,
        camera_id=camera_id,
        direction=direction,
        shift=shift,
    )

    response = EventListResponse(
        events=[_event_to_schema(e) for e in events[offset : offset + limit]],
        total=len(events),
        limit=limit,
        offset=offset,
    )
    return _envelope(response)


@app.post(
    f"{API_V1_PREFIX}/events",
    tags=["events"],
    response_model=ApiResponse[ProductionEventSchema],
    status_code=status.HTTP_201_CREATED,
    summary="Record a new production event.",
    responses={201: {"description": "Event created."}},
)
def create_event(
    event: ProductionEventSchema,
    event_repo: Annotated[EventRepository, Depends(get_event_repository)],
) -> JSONResponse:
    domain_event = ProductionEvent(
        timestamp=event.timestamp,
        line_id=event.line_id,
        camera_id=event.camera_id,
        detection_id=event.detection_id,
        direction=event.direction,
        bag_no=event.bag_no,
        shift=event.shift,
        production_batch=event.production_batch,
    )

    try:
        event_repo.append_event(domain_event)
    except OSError as exc:
        logger.exception("Failed to persist event")
        raise ApiError(
            "STORAGE_ERROR",
            "Could not persist the event.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    logger.info(
        "Event recorded: camera=%s bag_no=%s", event.camera_id, event.bag_no
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        headers={
            "Location": f"{API_V1_PREFIX}/events?camera_id={event.camera_id}"
        },
        content=_envelope(event),
    )



# ============================================================
# Reports
# ============================================================

def _period_start(period: str) -> datetime | None:
    """Return the inclusive start datetime for a period, or None for 'all'."""
    now = datetime.now()

    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return datetime.fromtimestamp(
            midnight.timestamp() - midnight.weekday() * 86400
        )
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def _build_summary(
    events: list[ProductionEvent], period: str
) -> ReportSummarySchema:
    """Aggregate events into report metrics (pure function)."""
    start = _period_start(period)

    if start is not None:
        events = [
            e for e in events
            if (_ts := _parse_event_timestamp(e.timestamp)) is not None
            and _ts >= start
        ]

    up = sum(1 for e in events if e.direction == "UP")
    by_shift: dict[str, int] = {}
    by_camera: dict[str, int] = {}

    for e in events:
        by_shift[e.shift] = by_shift.get(e.shift, 0) + 1
        by_camera[e.camera_id] = by_camera.get(e.camera_id, 0) + 1

    return ReportSummarySchema(
        period=period,  # type: ignore[arg-type]
        total_events=len(events),
        up_count=up,
        down_count=len(events) - up,
        unique_bags=len({e.bag_no for e in events}),
        by_shift=by_shift,
        by_camera=by_camera,
    )


@app.get(
    f"{API_V1_PREFIX}/reports/summary",
    tags=["reports"],
    response_model=ApiResponse[ReportSummarySchema],
    summary="Aggregate production metrics for a reporting period.",
)
def read_report_summary(
    event_repo: Annotated[EventRepository, Depends(get_event_repository)],
    period: str = "all",
) -> dict:
    if period not in VALID_PERIODS:
        raise ApiError(
            "INVALID_PERIOD",
            f"period must be one of: {', '.join(VALID_PERIODS)}.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    events = event_repo.read_events(as_dataframe=False)
    return _envelope(_build_summary(list(events), period))
