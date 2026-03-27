"""Test CPM client service"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.cpm_client_service import CPMClientService

_DB = MagicMock()


class TestCPMClientService:
    """Test CPMClientService class"""
    
    @patch('app.config_settings.feature_flags.MOCK_CPM_API_USED', True)
    @patch('app.routers.v1.cpm_mock.get_cpm_mock_data')
    async def test_get_cpm_by_filters_mock_success(self, mock_get_cpm_mock_data):
        """Test successful mock CPM retrieval"""
        # Setup mock response
        expected_response = {
            "lob": "CORPORATE",
            "sub_lob": "RATINGS",
            "cp_name": "Credit Opinion",
            "workflow_id": 3
        }
        mock_get_cpm_mock_data.return_value = expected_response
        
        # Call the method
        result = await CPMClientService.get_cpm_by_filters(
            _DB,
            lob="CORPORATE",
            sub_lob="RATINGS",
            cp_name="Credit Opinion",
        )
        
        # Assertions
        assert result == expected_response
        mock_get_cpm_mock_data.assert_called_once_with(
            "CORPORATE", "RATINGS", "Credit Opinion"
        )
    
    @patch('app.config_settings.feature_flags.MOCK_CPM_API_USED', True)
    @patch('app.routers.v1.cpm_mock.get_cpm_mock_data')
    async def test_get_cpm_by_filters_mock_not_found(self, mock_get_cpm_mock_data):
        """Test mock CPM not found scenario"""
        # Setup mock to raise exception
        mock_get_cpm_mock_data.side_effect = Exception("Not found")
        
        # Call and assert exception
        with pytest.raises(ValueError, match="Mock CPM record not found"):
            await CPMClientService.get_cpm_by_filters(
                _DB,
                lob="INVALID",
                sub_lob="INVALID",
                cp_name="INVALID",
            )
    
    @patch('app.config_settings.feature_flags.MOCK_CPM_API_USED', False)
    async def test_get_cpm_by_filters_real_api_not_implemented(self):
        """Test real API path raises NotImplementedError"""
        # Call and assert exception
        with pytest.raises(NotImplementedError, match="Real CPM API not yet implemented"):
            await CPMClientService.get_cpm_by_filters(
                _DB,
                lob="CORPORATE",
                sub_lob="RATINGS",
                cp_name="Credit Opinion",
            )
    
    def test_get_cpm_by_filters_is_static_method(self):
        """Test that get_cpm_by_filters is a static method"""
        # Should be callable without instantiation
        assert hasattr(CPMClientService, 'get_cpm_by_filters')
        assert callable(getattr(CPMClientService, 'get_cpm_by_filters'))
    
    @patch('app.config_settings.feature_flags.MOCK_CPM_API_USED', True)
    @patch('app.routers.v1.cpm_mock.get_cpm_mock_data')
    async def test_get_cpm_by_filters_mock_logging(self, mock_get_cpm_mock_data):
        """Test that mock API calls are logged correctly"""
        # Setup mock response
        mock_response = {"workflow_id": 3}
        mock_get_cpm_mock_data.return_value = mock_response
        
        with patch('app.services.cpm_client_service.logger') as mock_logger:
            # Call the method
            await CPMClientService.get_cpm_by_filters(
                _DB,
                lob="CORPORATE",
                sub_lob="RATINGS",
                cp_name="Credit Opinion",
            )
            
            # Check logging calls
            mock_logger.info.assert_any_call(
                "[MOCK] Fetching CPM data for lob=CORPORATE, sub_lob=RATINGS, cp_name=Credit Opinion"
            )
            mock_logger.info.assert_any_call(
                "[MOCK] CPM record retrieved with workflow_id: 3"
            )
    
    @patch('app.config_settings.feature_flags.MOCK_CPM_API_USED', True)
    @patch('app.routers.v1.cpm_mock.get_cpm_mock_data')
    async def test_get_cpm_by_filters_mock_error_logging(self, mock_get_cpm_mock_data):
        """Test that mock API errors are logged correctly"""
        # Setup mock to raise exception
        test_error = Exception("Test error")
        mock_get_cpm_mock_data.side_effect = test_error
        
        with patch('app.services.cpm_client_service.logger') as mock_logger:
            # Call and assert exception
            with pytest.raises(ValueError):
                await CPMClientService.get_cpm_by_filters(
                    _DB,
                    lob="CORPORATE",
                    sub_lob="RATINGS",
                    cp_name="Credit Opinion",
                )
            
            # Check error logging
            mock_logger.error.assert_called_once_with(
                "[MOCK] Error retrieving CPM record: Test error"
            )
    
    @patch('app.config_settings.feature_flags.MOCK_CPM_API_USED', False)
    async def test_get_cpm_by_filters_real_api_error_logging(self):
        """Test that real API path errors are logged correctly"""
        with patch('app.services.cpm_client_service.logger') as mock_logger:
            # Call and assert exception
            with pytest.raises(NotImplementedError):
                await CPMClientService.get_cpm_by_filters(
                    _DB,
                    lob="CORPORATE",
                    sub_lob="RATINGS",
                    cp_name="Credit Opinion",
                )
            
            # Check error logging
            mock_logger.error.assert_called_once_with(
                "[REAL API] Real CPM API not yet implemented"
            )
