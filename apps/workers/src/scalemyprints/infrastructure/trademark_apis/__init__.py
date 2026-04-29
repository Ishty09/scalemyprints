"""
Trademark office API adapters.

Each adapter:
- Implements TrademarkAPI protocol from the domain
- Owns its own HTTP client lifecycle
- Normalizes source-specific formats to domain TrademarkRecord
- Handles errors by returning TrademarkSearchResult with `error` set
  (never raises — that's the port contract)

Provider matrix:
  US → MarkerAPIClient (default, no key) | USPTOClient (with API key)
  EU → TMViewClient (default, public)    | EUIPOClient (legacy)
  UK → UKIPOClient
  AU → IPAustraliaClient
"""

from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory
from scalemyprints.infrastructure.trademark_apis.euipo import EUIPOClient
from scalemyprints.infrastructure.trademark_apis.ipau import IPAustraliaClient
from scalemyprints.infrastructure.trademark_apis.marker import MarkerAPIClient
from scalemyprints.infrastructure.trademark_apis.normalizers import (
    normalize_date_string,
    normalize_filing_status,
)
from scalemyprints.infrastructure.trademark_apis.tmview import TMViewClient
from scalemyprints.infrastructure.trademark_apis.ukipo import UKIPOClient
from scalemyprints.infrastructure.trademark_apis.uspto import USPTOClient

__all__ = [
    "EUIPOClient",
    "HttpClientFactory",
    "IPAustraliaClient",
    "MarkerAPIClient",
    "TMViewClient",
    "UKIPOClient",
    "USPTOClient",
    "normalize_date_string",
    "normalize_filing_status",
]
