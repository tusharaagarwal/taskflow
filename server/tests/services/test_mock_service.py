"""Test mock service"""
import pytest
from app.services.mock_service import MockService


class TestMockService:
    """Test MockService class"""
    
    def test_get_roles_returns_list(self):
        """Test that get_roles returns a list"""
        roles = MockService.get_roles()
        assert isinstance(roles, list)
    
    def test_get_roles_returns_expected_roles(self):
        """Test that get_roles returns expected role names"""
        roles = MockService.get_roles()
        expected_roles = [
            "GCC Associate",
            "Ratings Associate", 
            "Lead Author",
            "Copy Editor",
            "Internal Reviewer"
        ]
        assert roles == expected_roles
    
    def test_get_roles_returns_five_roles(self):
        """Test that get_roles returns exactly 5 roles"""
        roles = MockService.get_roles()
        assert len(roles) == 5
    
    def test_get_roles_contains_all_expected_roles(self):
        """Test that all expected roles are present"""
        roles = MockService.get_roles()
        expected_roles = {
            "GCC Associate",
            "Ratings Associate", 
            "Lead Author",
            "Copy Editor",
            "Internal Reviewer"
        }
        roles_set = set(roles)
        assert expected_roles.issubset(roles_set)
        assert len(roles_set) == 5  # No duplicates
    
    def test_get_roles_is_static_method(self):
        """Test that get_roles is a static method"""
        # Should be callable without instantiation
        assert hasattr(MockService, 'get_roles')
        assert callable(getattr(MockService, 'get_roles'))
        
        # Should work without creating an instance
        roles = MockService.get_roles()
        assert isinstance(roles, list)
