from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ..models import Severity
from ..storage import ScanStore
from .query import (
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidSecretQuery, SecretQuery, SecretQueryError,
    SecretQueryRepository,
)
from .schemas import SecretDetailResponse, SecretErrorResponse, SecretOverviewResponse
from .service import SecretQueryService


class SecretQueryRoute(APIRoute):
    """Route-local safe errors, including FastAPI's input/response validation.

    Other API routes keep their existing behavior. Do not log exception objects,
    validation inputs, stored payloads or source paths from this boundary.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        allowed = {parameter.alias for parameter in self.dependant.query_params}

        async def safe_handler(request: Request) -> Response:
            try:
                if any(key not in allowed or len(request.query_params.getlist(key)) != 1
                       for key in request.query_params):
                    raise InvalidSecretQuery()
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": InvalidSecretQuery.detail})
            except SecretQueryError as error:
                return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
            except Exception:
                # Includes response validation and persistence errors. Never stringify them.
                return JSONResponse(status_code=500, content={"detail": SecretQueryError.detail})

        return safe_handler


_ERROR_RESPONSES = {
    404: {"model": SecretErrorResponse, "description": "Scan or scoped Secret finding not found"},
    409: {"model": SecretErrorResponse, "description": "The saved scan has not reached a final state"},
    422: {"model": SecretErrorResponse, "description": "Invalid, unknown or repeated query parameter"},
    500: {"model": SecretErrorResponse, "description": "Stored results could not be read or converted"},
}


def create_secret_router(store: ScanStore) -> APIRouter:
    service = SecretQueryService(SecretQueryRepository(store))
    router = APIRouter(prefix="/api/scans", tags=["Secret results"], route_class=SecretQueryRoute)

    @router.get(
        "/{scan_id}/secrets", response_model=SecretOverviewResponse, responses=_ERROR_RESPONSES,
        summary="Query saved Secret findings",
        description=(
            "Reads persisted results without scanning or opening source files. Summary and by_type "
            "describe the whole scan; pagination.total counts filtered findings. Default order: "
            "severity descending, confidence descending, path/line/column/rule/id ascending. "
            "Module partial/disabled/unavailable/failed states are returned with diagnostics."
        ),
    )
    def overview(
        scan_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
        severity: Severity | None = Query(None),
        secret_type: str | None = Query(None, min_length=1, max_length=256),
        file_path: str | None = Query(None, min_length=1, max_length=256,
                                      description="Case-insensitive substring of any saved evidence path"),
        rule_id: str | None = Query(None, min_length=1, max_length=256),
        min_confidence: float | None = Query(None, ge=0, le=1, allow_inf_nan=False),
    ) -> SecretOverviewResponse:
        return service.overview(scan_id, SecretQuery(
            page=page, page_size=page_size, severity=severity, secret_type=secret_type,
            file_path=file_path, rule_id=rule_id, min_confidence=min_confidence,
        ))

    @router.get(
        "/{scan_id}/secrets/{finding_id}", response_model=SecretDetailResponse,
        responses=_ERROR_RESPONSES, summary="Read a saved Secret finding",
        description=(
            "Requires a Secret finding belonging to this scan. Includes all saved evidence locations, "
            "compact masked evidence and text remediation. Lines are 1-based; columns are 0-based "
            "and end-exclusive. Never reads original source or invokes remediation actions."
        ),
    )
    def detail(scan_id: str, finding_id: str) -> SecretDetailResponse:
        return service.detail(scan_id, finding_id)

    return router

