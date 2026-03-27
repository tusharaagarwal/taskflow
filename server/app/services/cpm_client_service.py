"""
TEMP MOCK: CPM Client Service
This service abstracts CPM API (mock or real) routing.
This file will be modified when switching to the real CPM API.
"""
import logging
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.security import sanitize_log_input

logger = logging.getLogger(__name__)


class CPMClientService:
    """Service for interacting with CPM API (mock or real)."""

    @staticmethod
    async def get_cpm_by_filters(
        db: AsyncSession, lob: str, sub_lob: str, cp_name: str
    ) -> Dict[str, Any]:
        """
        Get CPM record by filtering on LOB, sub-LOB, and content product name.

        Routes to mock or real API based on MOCK_CPM_API_USED flag.
        Mock path: ``workflow_id`` is None in returned record;
        caller resolves it via ``DEFAULT_MOCK_WORKFLOW_ID`` from feature_flags.

        Args:
            db: Database session (required by signature; unused in mock path)
            lob: Line of Business
            sub_lob: Sub Line of Business
            cp_name: Content Product Name

        Returns:
            Dictionary containing CPM record (workflow_id is None in mock path;
            resolved by caller via DEFAULT_MOCK_WORKFLOW_ID).

        Raises:
            ValueError: If CPM record not found
            NotImplementedError: If real API is requested but not yet implemented
        """
        from app.config_settings.feature_flags import MOCK_CPM_API_USED

        if MOCK_CPM_API_USED:
            logger.info(f"[MOCK] Fetching CPM data for lob={sanitize_log_input(lob)}, sub_lob={sanitize_log_input(sub_lob)}, cp_name={sanitize_log_input(cp_name)}")
            from app.routers.v1.cpm_mock import get_cpm_mock_data

            try:
                cpm_record = get_cpm_mock_data(lob, sub_lob, cp_name)
                logger.info(
                    f"[MOCK] CPM record retrieved for lob={sanitize_log_input(lob)}, sub_lob={sanitize_log_input(sub_lob)}, cp_name={sanitize_log_input(cp_name)}"
                )
                return cpm_record
            except Exception as e:
                logger.error(f"[MOCK] Error retrieving CPM record: {sanitize_log_input(str(e))}")
                raise ValueError(f"Mock CPM record not found for lob={lob}, sub_lob={sub_lob}, cp_name={cp_name}")
        else:
            logger.error("[REAL API] Real CPM API not yet implemented")
            raise NotImplementedError(
                "Real CPM API not yet implemented. "
                "Please set MOCK_CPM_API_USED = True in app/config_settings/feature_flags.py to use mock API."
            )
