"""
Unit tests for report tracker Pydantic schemas.
"""
import pytest
from pydantic import ValidationError
from app.schemas.report_tracker import (
    ReportTrackerCreateRequest,
    ReportTrackerUpdateRequest,
    AssignUserToStepRequest,
    generate_report_id,
)


class TestGenerateReportId:
    """Tests for report ID generation."""

    def test_generate_report_id_format(self):
        """Test report ID has correct format."""
        report_id = generate_report_id()

        assert report_id.startswith("RPT-")
        parts = report_id.split("-")
        assert len(parts) == 3


class TestReportTrackerCreateRequest:
    """Tests for create request schema."""

    def test_valid_create_request(self):
        """Test valid create request."""
        request = ReportTrackerCreateRequest(
            transaction_id="TXN-001",
            pr_id="PR-001",
            content_type="Credit Opinion",
            lob="banking",
            sub_lob="figbanking",
            document_type="Credit Opinion",
            action_code="APPROVED",
        )

        assert request.transaction_id == "TXN-001"
        assert request.pr_id == "PR-001"

    def test_create_workflow_steps_json_empty(self):
        """Test creating workflow steps with no workflow."""
        result = ReportTrackerCreateRequest.create_workflow_steps_json(None)

        assert "progress_tracker" in result
        assert result["progress_tracker"] == []

    def test_create_workflow_steps_json_with_steps(self):
        """Test creating workflow steps from workflow JSON."""
        workflow = {
            "steps": [
                {
                    "step_id": "draft",
                    "step_name": "Initial Draft",
                    "stage_name": "Authoring",
                    "transitions": {
                        "success_goto": "review",
                        "fail_goto": "NA",
                    },
                },
                {
                    "step_id": "review",
                    "step_name": "Review",
                    "stage_name": "Review",
                    "transitions": {
                        "success_goto": "NA",
                        "fail_goto": "draft",
                    },
                },
            ]
        }

        result = ReportTrackerCreateRequest.create_workflow_steps_json(workflow)

        assert len(result["progress_tracker"]) > 0


class TestReportTrackerUpdateRequest:
    """Tests for update request schema."""

    def test_valid_action_only(self):
        """Test valid update with action only."""
        request = ReportTrackerUpdateRequest(action="accept")

        assert request.action == "accept"

    def test_valid_app_data_only(self):
        """Test valid update with app_data only."""
        request = ReportTrackerUpdateRequest(
            instance_id="test-uuid",
            app_data={"key": "value"},
        )

        assert request.app_data == {"key": "value"}

    def test_invalid_neither_action_nor_app_data(self):
        """Test validation fails with neither action nor app_data."""
        with pytest.raises(ValidationError):
            ReportTrackerUpdateRequest()

    def test_valid_both_action_and_app_data(self):
        """Test valid update with both action and app_data."""
        request = ReportTrackerUpdateRequest(
            action="accept",
            instance_id="test-uuid",
            app_data={"comments": "Approved"},
        )

        assert request.action is not None
        assert request.app_data is not None


class TestAssignUserToStepRequest:
    """Tests for user assignment request schema."""

    def test_valid_assignment(self):
        """Test valid user assignment request."""
        request = AssignUserToStepRequest(
            report_id="REP-001",
            stage_name="Authoring",
            step_name="Initial Draft",
            user_id="user-123",
            user_name="John Doe",
            user_email="john@example.com",
            role="Analyst",
        )

        assert request.report_id == "REP-001"
        assert request.user_name == "John Doe"

    def test_missing_required_fields(self):
        """Test validation fails with missing required fields."""
        with pytest.raises(ValidationError):
            AssignUserToStepRequest(report_id="REP-001")
