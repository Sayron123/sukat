"""Provider-agnostic interface for reading a list photo."""

from typing import Literal, Protocol

from app.ai.schemas import (
    AIUsageInfo,
    CatalogEntry,
    MatchAnswer,
    MatchItem,
    ReadLine,
    ReadResult,
)

ImageType = Literal["image/jpeg", "image/png", "image/webp"]
ScanType = Literal["sale", "stock_in"]


class VisionReader(Protocol):
    def read_list(
        self,
        image: bytes,
        media_type: ImageType,
        catalog: list[CatalogEntry],
        scan_type: ScanType,
    ) -> ReadResult:
        """Read the list in `image`, matching items against `catalog`.

        @raises AIReadError on timeouts, refusals, or unusable output
        """
        ...


class ScanAI(Protocol):
    """The AI steps of the multi-step scan, one model call each. Implemented per
    provider (app/ai/anthropic_reader.py, app/ai/gemini_reader.py); the steps around
    them are plain code (app/ai/scan_pipeline.py)."""

    def read_photo(self, image: bytes, media_type: ImageType) -> tuple[list[ReadLine], AIUsageInfo]:
        """Step 1: every item row of the photo, copied as written (no product list).

        @raises AIReadError on timeouts, refusals, or unusable output
        """
        ...

    def match_items(
        self, items: list[MatchItem], catalog_text: str
    ) -> tuple[list[MatchAnswer], AIUsageInfo]:
        """Step 2 (only the lines code couldn't match): pick each item's product id
        from `catalog_text`, or null.

        @raises AIReadError on timeouts, refusals, or unusable output
        """
        ...
