"""
Printer-price port.

Both Printful and Printify implement the same interface so the
profit service can swap them at the container layer based on which
credentials are configured.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class LivePriceQuote(BaseModel):
    """A single live base-cost lookup result."""

    model_config = ConfigDict(frozen=True)

    printer: str  # 'printful' | 'printify' | ...
    product_type: str
    base_cost_usd: float = Field(ge=0.0)
    currency: str = "USD"
    source_url: str | None = None
    fetched_at: str
    error: str | None = None


@runtime_checkable
class PrinterPriceProvider(Protocol):
    """Fetch a fresh base cost for one (printer, product_type) pair."""

    @property
    def printer(self) -> str: ...

    async def quote(self, product_type: str) -> LivePriceQuote: ...
