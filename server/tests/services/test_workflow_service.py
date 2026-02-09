"""
Unit tests for WorkflowService.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.workflow_service import WorkflowService


class TestWorkflowService:
    """Tests for WorkflowService class."""

    def test_get_workflow_stage_permissions_returns_all_stages(self):
        """Test that get_workflow_stage_permissions returns all expected stages."""
        result = WorkflowService.get_workflow_stage_permissions()

        expected_stages = [
            "Initial Draft",
            "Final Draft",
            "Finalize Report",
            "Copy Editing",
            "L1 Approval",
            "Internal Final Review",
            "In Publication",
            "Publication Failed",
        ]
        assert all(stage in result for stage in expected_stages)

    def test_get_workflow_stage_permissions_gcc_associate_permissions(self):
        """Test GCC Associate has correct permissions per stage."""
        result = WorkflowService.get_workflow_stage_permissions()

        # GCC Associate can access Initial Draft and Final Draft
        assert result["Initial Draft"]["GCC Associate"] is True
        assert result["Final Draft"]["GCC Associate"] is True
        # But not other stages
        assert result["Finalize Report"]["GCC Associate"] is False
        assert result["Copy Editing"]["GCC Associate"] is False

    def test_get_workflow_stage_permissions_lead_author_permissions(self):
        """Test Lead Author has correct permissions."""
        result = WorkflowService.get_workflow_stage_permissions()

        assert result["Finalize Report"]["Lead Author"] is True
        assert result["In Publication"]["Lead Author"] is True

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_success(self):
        """Test successful retrieval of workflow JSON."""
        mock_db = AsyncMock()

        # Mock table exists check
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True

        # Mock workflow exists check
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True

        # Mock actual workflow data
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: {"steps": [{"step_id": "draft"}]}
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_table_not_exists(self):
        """Test returns empty dict when table doesn't exist."""
        mock_db = AsyncMock()

        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = False
        mock_db.execute.return_value = mock_table_exists

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_not_found(self):
        """Test returns empty dict when workflow doesn't exist."""
        mock_db = AsyncMock()

        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True

        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = False

        mock_db.execute.side_effect = [mock_table_exists, mock_workflow_exists]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 999)

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_handles_string_json(self):
        """Test parsing of JSON string workflow data."""
        mock_db = AsyncMock()

        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True

        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True

        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: '{"steps": []}'
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)

        assert isinstance(result, dict)
        assert "steps" in result

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_handles_exception(self):
        """Test exception handling during workflow retrieval."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database error")

        with pytest.raises(Exception):
            await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_empty_row(self):
        """Test returns empty dict when row is None."""
        mock_db = AsyncMock()
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_empty_row_data(self):
        """Test returns empty dict when row[0] is None."""
        mock_db = AsyncMock()
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: None
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_invalid_json_string(self):
        """Test returns empty dict when workflow_data string is invalid JSON."""
        mock_db = AsyncMock()
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: "not valid json {{{"
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_parsed_non_dict_list(self):
        """Test returns empty dict when parsed JSON is not dict or list."""
        mock_db = AsyncMock()
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: "123"
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_unexpected_type(self):
        """Test returns empty dict when workflow_data is unexpected type (e.g. int)."""
        mock_db = AsyncMock()
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: 12345
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_workflow_json_from_workflow_returns_list(self):
        """Test returns list when workflow_data is already a list."""
        mock_db = AsyncMock()
        mock_table_exists = MagicMock()
        mock_table_exists.scalar.return_value = True
        mock_workflow_exists = MagicMock()
        mock_workflow_exists.scalar.return_value = True
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, i: [{"step_id": "one"}]
        mock_result.fetchone.return_value = mock_row

        mock_db.execute.side_effect = [
            mock_table_exists,
            mock_workflow_exists,
            mock_result,
        ]

        result = await WorkflowService.get_workflow_json_from_workflow(mock_db, 1)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["step_id"] == "one"
