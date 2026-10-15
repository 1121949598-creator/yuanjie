from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from ..models import Severity
from ..storage import ScanStore
from .query import (
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidLicenseQuery, LicenseQuery, LicenseQueryError,
    LicenseQueryRepository,
)
from .schemas import LicenseDetailResponse, LicenseErrorResponse, LicenseOverviewResponse
from .service import LicenseQueryService


class LicenseQueryRoute(APIRoute):
    """License-local fixed error boundary; Secret routing remains frozen."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        allowed = {parameter.alias for parameter in self.dependant.query_params}

        async def safe_handler(request: Request) -> Response:
            try:
                for key in request.query_params:
                    values = request.query_params.getlist(key)
                    if key not in allowed or len(values) != 1:
                        raise InvalidLicenseQuery()
                    if key == "manual_review_required" and values[0] not in {"true", "false"}:
                        raise InvalidLicenseQuery()
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": InvalidLicenseQuery.detail})
            except LicenseQueryError as error:
                return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
            except Exception:
                return JSONResponse(status_code=500, content={"detail": LicenseQueryError.detail})

        return safe_handler


_ERROR_RESPONSES = {
    404: {"model": LicenseErrorResponse, "description": "Scan or scoped License assessment not found"},
    409: {"model": LicenseErrorResponse, "description": "Scan not final or inventory schema unsupported"},
    422: {"model": LicenseErrorResponse, "description": "Invalid, unknown or repeated query parameter"},
    500: {"model": LicenseErrorResponse, "description": "Stored License results could not be converted"},
}


def create_license_router(store: ScanStore) -> APIRouter:
    service = LicenseQueryService(LicenseQueryRepository(store))
    router = APIRouter(prefix="/api/scans", tags=["License results"], route_class=LicenseQueryRoute)

    @router.get(
        "/{scan_id}/licenses", response_model=LicenseOverviewResponse, responses=_ERROR_RESPONSES,
        summary="Query saved License assessments",
        description=(
            "Reads persisted License inventory schema v1 without scanning, opening source files, "
            "running policy, or contacting providers. Items are assessments, including permissive "
            "and unlocated reviews. Filters are combined with AND. Default order is severity and "
            "manual-review priority descending, then package, expression, path and assessment ID."
        ),
    )
    def overview(
        scan_id: str = Path(..., min_length=1, max_length=256),
        page: int = Query(1, ge=1),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
        classification: str | None = Query(None, min_length=1, max_length=256),
        severity: Severity | None = Query(None),
        manual_review_required: bool | None = Query(None),
        package_name: str | None = Query(
            None, min_length=1, max_length=256,
            description="Case-insensitive substring of the saved package name",
        ),
        license_expression: str | None = Query(
            None, min_length=1, max_length=256,
            description="Case-insensitive substring of canonical, or retained original, expression",
        ),
        file_path: str | None = Query(
            None, min_length=1, max_length=256,
            description="Case-insensitive substring of the saved relative location",
        ),
    ) -> LicenseOverviewResponse:
        return service.overview(scan_id, LicenseQuery(
            page=page, page_size=page_size, classification=classification, severity=severity,
            manual_review_required=manual_review_required, package_name=package_name,
            license_expression=license_expression, file_path=file_path,
        ))

    @router.get(
        "/{scan_id}/licenses/{assessment_id}", response_model=LicenseDetailResponse,
        responses=_ERROR_RESPONSES, summary="Read a saved License assessment",
        description=(
            "Reads one assessment belonging to this scan and projects its saved package, License "
            "observation, normalization, location, License finding references and explicit provider "
            "provenance. The assessment ID is used because permissive and unlocated assessments may "
            "have no finding or License observation."
        ),
    )
    def detail(
        scan_id: str = Path(..., min_length=1, max_length=256),
        assessment_id: str = Path(..., min_length=1, max_length=256),
    ) -> LicenseDetailResponse:
        return service.detail(scan_id, assessment_id)

    return router
