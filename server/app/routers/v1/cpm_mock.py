"""
TEMP MOCK: CPM API Mock Router
This file will be deleted when switching to the real CPM API.
"""
import uuid
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any

from app.config_settings.feature_flags import DEFAULT_MOCK_WORKFLOW_ID

router = APIRouter(prefix="/cpm", tags=["CPM Mock"])

# Namespace for deterministic UUID generation
NAMESPACE_CPM = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_deterministic_uuid(seed: str) -> str:
    """Generate a deterministic UUID based on a seed string."""
    return str(uuid.uuid5(NAMESPACE_CPM, seed))


def get_cpm_mock_data(lob: str, sub_lob: str, cp_name: str) -> Dict[str, Any]:
    """
    Generate mock CPM data based on lob, sub_lob, and cp_name.
    
    Args:
        lob: Line of Business
        sub_lob: Sub Line of Business
        cp_name: Content Product Name
        
    Returns:
        Dictionary containing mock CPM record
    """
    # Use default workflow_id (integer)
    workflow_id = DEFAULT_MOCK_WORKFLOW_ID
    
    # Generate deterministic UUIDs
    cp_id = generate_deterministic_uuid(f"{lob}-{sub_lob}-{cp_name}")
    report_type_id = generate_deterministic_uuid(f"report_type-{cp_name}")
    lob_id = generate_deterministic_uuid(f"lob-{lob}")
    sub_lob_id = generate_deterministic_uuid(f"sub_lob-{sub_lob}")
    
    # Content blocks
    block_1_id = generate_deterministic_uuid(f"block-summary-{cp_name}")
    block_2_id = generate_deterministic_uuid(f"block-ratings-{cp_name}")
    
    # Primitives for block 1
    prim_1_1_id = generate_deterministic_uuid(f"prim-h1-summary-{cp_name}")
    prim_1_2_id = generate_deterministic_uuid(f"prim-h2-summary-{cp_name}")
    
    # Primitives for block 2
    prim_2_1_id = generate_deterministic_uuid(f"prim-h1-ratings-{cp_name}")
    prim_2_2_id = generate_deterministic_uuid(f"prim-h2-ratings-{cp_name}")
    prim_2_3_id = generate_deterministic_uuid(f"prim-table-ratings-{cp_name}")
    
    return {
        "cp_id": cp_id,
        "cp_name": cp_name,
        "report_type": cp_name,
        "report_type_id": report_type_id,
        "lob": lob,
        "lob_id": lob_id,
        "sub_lob": sub_lob,
        "sub_lob_id": sub_lob_id,
        "output_formats": ["pdf", "html"],
        "workflow_id": workflow_id,
        "content_blocks": [
            {
                "block_id": block_1_id,
                "block_name": "Summary",
                "block_type": "text",
                "is_mandatory": True,
                "sequence": 1,
                "scope": "public",
                "is_editable": True,
                "rules": [
                    {"type": "word_limit", "min": 10, "max": 100},
                    {"type": "char_limit", "min": 10, "max": 100}
                ],
                "primitives_allowed": [
                    {
                        "primitive_id": prim_1_1_id,
                        "primitive_type": "H1",
                        "is_mandatory": True,
                        "is_editable": True,
                        "primitive_label": "Summary"
                    },
                    {
                        "primitive_id": prim_1_2_id,
                        "primitive_type": "H2",
                        "is_mandatory": False,
                        "is_editable": True,
                        "primitive_label": None
                    }
                ]
            },
            {
                "block_id": block_2_id,
                "block_name": "Ratings",
                "block_type": "all",
                "is_mandatory": True,
                "sequence": 2,
                "scope": "private",
                "is_editable": False,
                "rules": [
                    {"type": "word_limit", "min": 10, "max": 100},
                    {"type": "char_limit", "min": 10, "max": None}
                ],
                "primitives_allowed": [
                    {
                        "primitive_id": prim_2_1_id,
                        "primitive_type": "H1",
                        "is_mandatory": True,
                        "is_editable": True,
                        "primitive_label": "Summary"
                    },
                    {
                        "primitive_id": prim_2_2_id,
                        "primitive_type": "H2",
                        "is_mandatory": False,
                        "is_editable": True,
                        "primitive_label": None
                    },
                    {
                        "primitive_id": prim_2_3_id,
                        "primitive_type": "table",
                        "is_mandatory": False,
                        "is_editable": True,
                        "primitive_label": None
                    }
                ]
            }
        ]
    }


# TEMP MOCK: will be trashed later
@router.get("/search")
async def search_cpm(
    lob: str = Query(..., description="Line of Business"),
    sub_lob: str = Query(..., description="Sub Line of Business"),
    cp_name: str = Query(..., description="Content Product Name")
) -> Dict[str, Any]:
    """
    Search for a CPM record by LOB, sub-LOB, and content product name.
    Returns a single CPM record matching the filters.
    """
    return get_cpm_mock_data(lob, sub_lob, cp_name)


# TEMP MOCK: will be trashed later
@router.get("/{cp_id}")
async def get_cpm_detail(cp_id: str) -> Dict[str, Any]:
    """
    Get CPM record by CP ID.
    Returns mock data with the provided cp_id.
    """
    # For the detail endpoint, we'll return a default record
    # but use the provided cp_id in the response
    
    # Use default workflow for detail endpoint
    default_lob = "banking"
    default_sub_lob = "figbanking"
    default_cp_name = "Credit Opinion"
    
    mock_data = get_cpm_mock_data(default_lob, default_sub_lob, default_cp_name)
    
    # Override the cp_id with the one from the path
    mock_data["cp_id"] = cp_id
    
    return mock_data

