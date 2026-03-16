"""Document type abbreviation seed rows."""

from __future__ import annotations

from typing import TypedDict


class AbbreviationSeedRow(TypedDict):
    document_type: str
    abbreviation: str
    is_active: bool


ABBREVIATION_SEED_ROWS: tuple[AbbreviationSeedRow, ...] = (
    {
        "document_type": "Credit Opinion",
        "abbreviation": "CO",
        "is_active": True,
    },
)

