"""
Additional tests for ReportTrackerService to increase coverage.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.report_tracker_service import ReportTrackerService


class TestReportTrackerServiceAdditional:
    """Additional tests for ReportTrackerService."""

    @pytest.fixture
    def service(self):
        return ReportTrackerService()

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_generate_report_id_raises_value_error(self, mock_db):
        """Create raises ValueError when _generate_unique_report_id raises."""
        with patch.object(
            ReportTrackerService,
            "_generate_unique_report_id",
            new_callable=AsyncMock,
            side_effect=RuntimeError("abbreviation service down"),
        ):
            from app.schemas.report_tracker import ReportTrackerCreateRequest
            create_data = ReportTrackerCreateRequest(
                transaction_id="T1",
                pr_id="PR-1",
                content_type="Credit Opinion",
                lob="LOB",
                sub_lob="Sub",
                document_type="Credit Opinion",
                action_code="APPROVED",
            )
            with pytest.raises(ValueError, match="Failed to generate report_id"):
                await ReportTrackerService.create(mock_db, create_data)

    def test_find_step_in_workflow_json_found(self, service):
        """Test finding a step in workflow JSON."""
        workflow = {
            "steps": [
                {"step_id": "draft", "step_name": "Draft"},
                {"step_id": "review", "step_name": "Review"},
            ]
        }

        result = ReportTrackerService._find_step_in_workflow_json(
            workflow, "draft"
        )

        assert result is not None
        assert result["step_name"] == "Draft"

    def test_find_step_in_workflow_json_not_found(self, service):
        """Test finding non-existent step."""
        workflow = {"steps": [{"step_id": "draft"}]}

        result = ReportTrackerService._find_step_in_workflow_json(
            workflow, "nonexistent"
        )

        assert result is None

    def test_find_step_in_workflow_json_empty_steps(self, service):
        """Test finding step when workflow has no steps key."""
        result = ReportTrackerService._find_step_in_workflow_json(
            {}, "draft"
        )
        assert result is None

        result = ReportTrackerService._find_step_in_workflow_json(
            {"steps": []}, "draft"
        )
        assert result is None

    def test_is_auto_complete_stage_true(self, service):
        """Test auto-complete stage detection."""
        assert ReportTrackerService._is_auto_complete_stage("Published") is True

    def test_is_auto_complete_stage_false(self, service):
        """Test non-auto-complete stage detection."""
        assert ReportTrackerService._is_auto_complete_stage("Initial Draft") is False
        assert ReportTrackerService._is_auto_complete_stage("In Publication") is False

    def test_resolve_transition_path_simple_string(self, service):
        """Test resolving simple string transition."""
        result = ReportTrackerService._resolve_transition_path("next_step")

        assert result == "next_step"

    def test_resolve_transition_path_nested_dict_default(self, service):
        """Test resolving nested dict transition with default."""
        transition = {
            "default": "approved_step",
            "reject": "rejected_step",
        }

        result = ReportTrackerService._resolve_transition_path(transition)

        assert result == "approved_step"

    def test_resolve_transition_path_with_explicit_path(self, service):
        """Test resolving transition with explicit path."""
        transition = {
            "default": "approved_step",
            "reject": "rejected_step",
        }

        result = ReportTrackerService._resolve_transition_path(
            transition, path="reject"
        )

        assert result == "rejected_step"

    def test_get_default_transition_string(self, service):
        """Test getting default transition from string."""
        result = ReportTrackerService._get_default_transition("next_step")

        assert result == "next_step"

    def test_get_default_transition_dict(self, service):
        """Test getting default transition from dict."""
        result = ReportTrackerService._get_default_transition({
            "default": "default_step",
            "other": "other_step",
        })

        assert result == "default_step"

    def test_get_default_transition_none(self, service):
        """Test getting default transition when no default key."""
        result = ReportTrackerService._get_default_transition({"other": "x"})

        assert result is None

    def test_create_step_object(self, service):
        """Test creating step object from definition."""
        step_json = {
            "step_id": "draft",
            "step_name": "Initial Draft",
            "stage_name": "Authoring",
        }

        result = ReportTrackerService._create_step_object(step_json)

        assert result["step_id"] == "draft"
        assert "instance_id" in result
        assert result["status"] == "in_progress"

    def test_create_step_object_with_status(self, service):
        """Test creating step object with custom status."""
        step_json = {"step_id": "draft", "step_name": "Draft"}

        result = ReportTrackerService._create_step_object(
            step_json, status="completed"
        )

        assert result["status"] == "completed"

    def test_create_step_object_auto_complete_stage(self, service):
        """Test creating step object for auto-complete stage (Published)."""
        step_json = {
            "step_id": "pub",
            "step_name": "Publish",
            "stage_name": "Published",
        }

        result = ReportTrackerService._create_step_object(step_json)

        assert result["status"] == "completed"
        assert result["completed_at"] is not None

    def test_are_all_steps_completed_empty(self, service):
        """Empty steps returns False."""
        assert ReportTrackerService._are_all_steps_completed([], {}) is False

    def test_are_all_steps_completed_in_progress(self, service):
        """Step still in_progress returns False."""
        steps = [
            {"step_id": "draft", "status": "completed"},
            {"step_id": "review", "status": "in_progress"},
        ]
        workflow = {"steps": [{"step_id": "review", "transitions": {"success_goto": "NA"}}]}
        assert ReportTrackerService._are_all_steps_completed(steps, workflow) is False

    def test_are_all_steps_completed_retry(self, service):
        """Step in retry returns False."""
        steps = [
            {"step_id": "draft", "status": "completed"},
            {"step_id": "review", "status": "retry"},
        ]
        workflow = {"steps": [{"step_id": "review", "transitions": {}}]}
        assert ReportTrackerService._are_all_steps_completed(steps, workflow) is False

    def test_are_all_steps_completed_last_not_completed(self, service):
        """Last step not completed returns False."""
        steps = [
            {"step_id": "draft", "status": "completed"},
            {"step_id": "review", "status": "yet_to_start"},
        ]
        workflow = {"steps": [{"step_id": "review", "transitions": {"success_goto": "NA"}}]}
        assert ReportTrackerService._are_all_steps_completed(steps, workflow) is False

    def test_are_all_steps_completed_last_has_next_step(self, service):
        """Last step has success_goto not NA returns False."""
        steps = [
            {"step_id": "draft", "status": "completed"},
            {"step_id": "review", "status": "completed"},
        ]
        workflow = {
            "steps": [
                {"step_id": "review", "transitions": {"success_goto": "approval"}},
            ]
        }
        assert ReportTrackerService._are_all_steps_completed(steps, workflow) is False

    def test_are_all_steps_completed_fully_complete(self, service):
        """All completed and last has NA success_goto returns True."""
        steps = [
            {"step_id": "draft", "status": "completed"},
            {"step_id": "review", "status": "completed"},
        ]
        workflow = {
            "steps": [
                {"step_id": "review", "transitions": {"success_goto": "NA"}},
            ]
        }
        assert ReportTrackerService._are_all_steps_completed(steps, workflow) is True

    def test_build_happy_path_empty_workflow(self, service):
        """Empty workflow returns empty list."""
        result = ReportTrackerService._build_happy_path({}, "draft", "2024-01-01T00:00:00Z")
        assert result == []
        result = ReportTrackerService._build_happy_path({"steps": []}, "draft", "2024-01-01T00:00:00Z")
        assert result == []

    def test_build_happy_path_single_step(self, service):
        """Single step with NA success_goto returns one step."""
        workflow = {
            "steps": [
                {
                    "step_id": "draft",
                    "step_name": "Draft",
                    "stage_name": "Authoring",
                    "transitions": {"success_goto": "NA"},
                }
            ]
        }
        result = ReportTrackerService._build_happy_path(
            workflow, "draft", "2024-01-01T00:00:00Z"
        )
        assert len(result) == 1
        assert result[0]["step_id"] == "draft"
        assert result[0]["status"] == "in_progress"

    def test_build_happy_path_multiple_steps(self, service):
        """Multiple steps follow success_goto chain."""
        workflow = {
            "steps": [
                {"step_id": "draft", "step_name": "Draft", "stage_name": "A", "transitions": {"success_goto": "review"}},
                {"step_id": "review", "step_name": "Review", "stage_name": "B", "transitions": {"success_goto": "NA"}},
            ]
        }
        result = ReportTrackerService._build_happy_path(
            workflow, "draft", "2024-01-01T00:00:00Z"
        )
        assert len(result) == 2
        assert result[0]["step_id"] == "draft"
        assert result[0]["status"] == "in_progress"
        assert result[1]["step_id"] == "review"
        assert result[1]["status"] == "yet_to_start"

    @pytest.mark.asyncio
    async def test_get_status_returns_none_when_tracker_not_found(self, mock_db):
        """get_status returns None when get_by_report_id returns None."""
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await ReportTrackerService.get_status(
                mock_db, "nonexistent-id", include_audit=True
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_status_returns_dict_when_tracker_found(self, mock_db):
        """get_status returns report_id and progress_tracker when tracker exists."""
        from app.models.report_tracker import ReportTracker
        mock_tracker = MagicMock(spec=ReportTracker)
        mock_tracker.report_id = "R-1"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {"step_id": "draft", "status": "in_progress"},
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_status(
                mock_db, "R-1", include_audit=False
            )
        assert result is not None
        assert result["report_id"] == "R-1"
        assert "progress_tracker" in result
        assert len(result["progress_tracker"]) == 1

    @pytest.mark.asyncio
    async def test_get_status_handles_none_workflow_steps_json(self, mock_db):
        """get_status handles tracker with workflow_steps_json None."""
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-2"
        mock_tracker.workflow_steps_json = None
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_status(mock_db, "R-2")
        assert result["report_id"] == "R-2"
        assert result["progress_tracker"] == []

    @pytest.mark.asyncio
    async def test_assign_user_to_step_returns_none_when_tracker_not_found(self, mock_db):
        """assign_user_to_step returns None when report not found."""
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await ReportTrackerService.assign_user_to_step(
                db=mock_db,
                report_id="nonexistent",
                stage_name="Authoring",
                step_name="Initial Draft",
                user_id="u1",
                user_name="User One",
                user_email="u1@example.com",
                role="Analyst",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_assign_user_to_step_raises_when_no_matching_step(self, mock_db):
        """assign_user_to_step raises UnprocessableEntity when no in_progress step matches."""
        from app.exceptions import UnprocessableEntityException
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-1"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {"step_id": "draft", "stage_name": "Authoring", "step_name": "Draft", "status": "completed"},
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            with pytest.raises(UnprocessableEntityException):
                await ReportTrackerService.assign_user_to_step(
                    db=mock_db,
                    report_id="R-1",
                    stage_name="Authoring",
                    step_name="Initial Draft",
                    user_id="u1",
                    user_name="User One",
                    user_email="u1@example.com",
                    role=None,
                )

    @pytest.mark.asyncio
    async def test_assign_user_to_step_success(self, mock_db):
        """assign_user_to_step appends assignee and returns tracker."""
        with patch(
            "app.services.report_tracker_service.flag_modified",
        ):
            progress = [
                {
                    "step_id": "draft",
                    "stage_name": "Authoring",
                    "step_name": "Initial Draft",
                    "status": "in_progress",
                }
            ]
            mock_tracker = MagicMock()
            mock_tracker.report_id = "R-1"
            mock_tracker.workflow_steps_json = {"progress_tracker": progress}
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()
            with patch.object(
                ReportTrackerService,
                "get_by_report_id",
                new_callable=AsyncMock,
                return_value=mock_tracker,
            ):
                result = await ReportTrackerService.assign_user_to_step(
                    db=mock_db,
                    report_id="R-1",
                    stage_name="Authoring",
                    step_name="Initial Draft",
                    user_id="u1",
                    user_name="User One",
                    user_email="u1@example.com",
                    role="Analyst",
                )
            assert result is mock_tracker
            assert len(progress) == 1
            assert progress[0].get("app_data", {}).get("assignee")
            assert len(progress[0]["app_data"]["assignee"]) == 1
            assert progress[0]["app_data"]["assignee"][0]["user_id"] == "u1"
