"""
API request/response DTOs.

These are THIN wrappers around domain models, adapted for HTTP:
- May omit internal fields
- May add response metadata
- Use Pydantic's aliasing for snake_case/camelCase if needed

Always mirror shapes defined in packages/contracts/src/ (TypeScript).
"""

from scalemyprints.api.schemas.envelope import (
    ApiError,
    ApiMeta,
    ApiResponse,
    PaginationMeta,
    failure,
    success,
)
from scalemyprints.api.schemas.trademark import (
    CreateMonitorBody,
    MonitorResponse,
    SearchBody,
    SearchHistoryResponse,
    SearchResponse,
)

__all__ = [
    # Envelope
    "ApiError",
    "ApiMeta",
    "ApiResponse",
    "PaginationMeta",
    "failure",
    "success",
    # Trademark
    "CreateMonitorBody",
    "MonitorResponse",
    "SearchBody",
    "SearchHistoryResponse",
    "SearchResponse",
]
