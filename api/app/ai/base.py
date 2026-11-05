"""Provider-agnostic interface for reading a list photo."""

from typing import Literal, Protocol

from app.ai.schemas import CatalogEntry, ReadResult

ImageType = Literal["image/jpeg", "image/png", "image/webp"]


class VisionReader(Protocol):
    def read_list(
        self,
        image: bytes,
        media_type: ImageType,
        catalog: list[CatalogEntry],
        scan_type: Literal["sale", "stock_in"],
    ) -> ReadResult:
        """Read the list in `image`, matching items against `catalog`.

        @raises AIReadError on timeouts, refusals, or unusable output
        """
        ...
