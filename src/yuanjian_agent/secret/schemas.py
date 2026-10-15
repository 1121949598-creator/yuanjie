from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from ..core.scanner import ScanStatus
from ..models import Severity
from .query import MAX_PAGE_SIZE


def compact_mask(value: object) -> str:
    """Accept only the compact masked representation already produced by storage.

    This is an output-shape guard, not a credential detector or a source redactor.
    Legacy full-line evidence and malformed values are withheld.
    """
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        return "****"
    start = value.find("*")
    end = value.rfind("*") + 1
    if (0 <= start <= 4 and 0 <= len(value) - end <= 4
            and 4 <= end - start <= 12 and set(value[start:end]) == {"*"}):
        return value
    return "****"


MaskedText = Annotated[str, BeforeValidator(compact_mask)]


class SecretResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class SecretErrorResponse(SecretResponseModel):
    detail: str


class SecretLocationResponse(SecretResponseModel):
    file_path: str = Field(repr=False)
    line: int = Field(ge=1, description="1-based start line")
    end_line: int = Field(ge=1, description="1-based end line")
    column_start: int = Field(ge=0, description="0-based start column")
    column_end: int = Field(ge=0, description="Exclusive 0-based column on end_line")


class SecretEvidenceResponse(SecretResponseModel):
    location: SecretLocationResponse
    masked_value: MaskedText = Field(examples=["sk-****abcd"])
    masked_excerpt: MaskedText = Field(examples=["sk-****abcd"])


class SecretFindingItem(SecretResponseModel):
    finding_id: str
    rule_id: str
    secret_type: str
    severity: Severity
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    message: str = Field(repr=False)
    location: SecretLocationResponse | None
    masked_value: MaskedText = Field(examples=["sk-****abcd"])
    occurrence_count: int = Field(ge=0)


class SecretSummaryResponse(SecretResponseModel):
    total: int = Field(default=0, ge=0)
    critical: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    low: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)


class SecretPaginationResponse(SecretResponseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total: int = Field(ge=0, description="Number of findings after filters, before pagination")


class SecretOverviewResponse(SecretResponseModel):
    scan_id: str
    module: Literal["secret"] = "secret"
    status: ScanStatus
    scan_status: str
    diagnostics: list[str]
    summary: SecretSummaryResponse = Field(description="Whole-scan Secret counts, independent of filters")
    by_type: dict[str, int] = Field(description="Whole-scan distribution; only observed Secret types")
    pagination: SecretPaginationResponse
    items: list[SecretFindingItem]


class SecretRemediationResponse(SecretResponseModel):
    title: str
    steps: list[str]


class SecretDetailResponse(SecretFindingItem):
    scan_id: str
    module: Literal["secret"] = "secret"
    status: ScanStatus
    scan_status: str
    diagnostics: list[str]
    evidence: list[SecretEvidenceResponse] = Field(description="All saved occurrences, ordered by location")
    remediation: SecretRemediationResponse

