import logging
import re
import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.health import router as health_router
from app.api.datasets import router as datasets_router
from app.api.benchmarks import router as benchmarks_router
from app.api.runs import router as runs_router
from app.api.projects import router as projects_router
from app.core.config import get_settings
from app.core.logging import configure_logging, request_id_context

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("reli.api")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.include_router(health_router)
app.include_router(datasets_router)
app.include_router(runs_router)
app.include_router(projects_router)
app.include_router(benchmarks_router)


@app.middleware("http")
async def request_context(request: Request, call_next: Callable):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        if request.url.path in {"/datasets/import", "/datasets/import/preview", "/datasets/import/columns"}:
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit():
                maximum_request = get_settings().dataset_import_max_bytes + 1024 * 1024
                if int(content_length) > maximum_request:
                    response = error_response(
                        request,
                        413,
                        f"Upload exceeds the configured {get_settings().dataset_import_max_bytes}-byte file limit",
                    )
                    response.headers["X-Request-ID"] = request_id
                    return response
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response
    finally:
        request_id_context.reset(token)


def error_response(
    request: Request,
    status_code: int,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    details = exc.detail if not isinstance(exc.detail, str) else None
    response = error_response(request, exc.status_code, str(exc.detail), details)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        request, 422, "Request validation failed", jsonable_encoder(exc.errors())
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled request error")
    return error_response(request, 500, "Internal server error")
