"""
TEMP MOCK: CPM Client Service
This service abstracts CPM API calls and handles mock vs real API routing.
This file will be modified when switching to the real CPM API.
"""
import logging
from typing import Dict, Any

from app.utils.security import sanitize_log_input

logger = logging.getLogger(__name__)


class CPMClientService:
    """Service for interacting with CPM API (mock or real)."""
    
    @staticmethod
    async def get_cpm_by_filters(lob: str, sub_lob: str, cp_name: str) -> Dict[str, Any]:
        """
        Get CPM record by filtering on LOB, sub-LOB, and content product name.
        
        Routes to mock or real API based on MOCK_CPM_API_USED flag.
        
        Args:
            lob: Line of Business
            sub_lob: Sub Line of Business
            cp_name: Content Product Name
            
        Returns:
            Dictionary containing CPM record with workflow_id
            
        Raises:
            ValueError: If CPM record not found
            NotImplementedError: If real API is requested but not yet implemented
        """
        from app.config_settings.feature_flags import MOCK_CPM_API_USED
        
        if MOCK_CPM_API_USED:
            # Use mock API - direct function call (faster than HTTP)
            logger.info(f"[MOCK] Fetching CPM data for lob={sanitize_log_input(lob)}, sub_lob={sanitize_log_input(sub_lob)}, cp_name={sanitize_log_input(cp_name)}")
            from app.routers.v1.cpm_mock import get_cpm_mock_data
            
            try:
                cpm_record = get_cpm_mock_data(lob, sub_lob, cp_name)
                logger.info(f"[MOCK] CPM record retrieved with workflow_id: {sanitize_log_input(str(cpm_record.get('workflow_id', '')))}")
                return cpm_record
            except Exception as e:
                logger.error(f"[MOCK] Error retrieving CPM record: {sanitize_log_input(str(e))}")
                raise ValueError(f"Mock CPM record not found for lob={lob}, sub_lob={sub_lob}, cp_name={cp_name}")
        else:
            # TODO: Call real external CPM API
            # Implementation will go here when real API is available
            logger.error("[REAL API] Real CPM API not yet implemented")
            raise NotImplementedError(
                "Real CPM API not yet implemented. "
                "Please set MOCK_CPM_API_USED = True in app/config/feature_flags.py to use mock API."
            )
            
            # Example implementation for when real API is available:
            # import httpx
            # real_cpm_url = "https://real-cpm-api.com/v1/cpm/search"
            # params = {
            #     "lob": lob,
            #     "sub_lob": sub_lob,
            #     "cp_name": cp_name
            # }
            # async with httpx.AsyncClient() as client:
            #     response = await client.get(real_cpm_url, params=params)
            #     response.raise_for_status()
            #     return response.json()

