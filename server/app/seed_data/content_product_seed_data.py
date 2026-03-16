"""Content product seed rows."""

from __future__ import annotations

from typing import TypedDict


class ContentProductSeedRow(TypedDict):
    id: int
    name: str
    workflow_id: int


CONTENT_PRODUCT_SEED_ROWS: tuple[ContentProductSeedRow, ...] = (
    {
        "id": 1,
        "name": "Credit Opinion",
        "workflow_id": 2,
    },
)

