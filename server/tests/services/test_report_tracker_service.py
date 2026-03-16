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

    def test_reject_finds_completed_step_index_tier4(self, service):
        """_reject with completed last step (e.g. Published) finds index via Tier 4 and runs rejection flow."""
        from unittest.mock import MagicMock
        workflow_json = {
            "steps": [
                {
                    "step_id": "published",
                    "step_name": "Published",
                    "stage_name": "Published",
                    "transitions": {
                        "fail_goto": {"default": "NA", "unpublish": "unpublish_in_progress"}
                    },
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
                {
                    "step_id": "unpublish_in_progress",
                    "step_name": "Un-Publish",
                    "stage_name": "Un-Publish",
                    "transitions": {"success_goto": "NA"},
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
            ]
        }
        steps = [
            {"step_id": "prev", "status": "completed", "instance_id": "i1"},
            {"step_id": "published", "status": "completed", "instance_id": "i2"},
        ]
        current_step = steps[1]
        current_step_json = workflow_json["steps"][0]
        tracker = MagicMock()
        ReportTrackerService._reject(
            tracker, steps, current_step, current_step_json, workflow_json, path="unpublish"
        )
        assert steps[1]["status"] == "rejected"
        assert len(steps) == 3
        assert steps[2]["step_id"] == "unpublish_in_progress"
        assert steps[2]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_reject_with_path_on_last_completed_step(self, mock_db):
        """update() with action=reject and path targets last completed step when no in_progress step."""
        from app.schemas.report_tracker import ReportTrackerUpdateRequest
        from app.models.report_tracker import ReportTracker
        from unittest.mock import MagicMock

        workflow_json = {
            "steps": [
                {
                    "step_id": "published",
                    "step_name": "Published",
                    "stage_name": "Published",
                    "transitions": {
                        "fail_goto": {"default": "NA", "unpublish": "unpublish_in_progress"}
                    },
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
                {
                    "step_id": "unpublish_in_progress",
                    "step_name": "Un-Publish",
                    "stage_name": "Un-Publish",
                    "transitions": {"success_goto": "NA"},
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
            ]
        }
        progress = [
            {"step_id": "prev", "status": "completed", "instance_id": "i1"},
            {"step_id": "published", "status": "completed", "instance_id": "i2"},
        ]
        mock_tracker = MagicMock(spec=ReportTracker)
        mock_tracker.workflow_steps_json = {"progress_tracker": progress}
        mock_tracker.workflow_json = workflow_json
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        with patch("app.services.report_tracker_service.flag_modified"):
            with patch.object(
                ReportTrackerService,
                "get_by_report_id",
                new_callable=AsyncMock,
                return_value=mock_tracker,
            ):
                update_data = ReportTrackerUpdateRequest(
                    action="reject",
                    path="unpublish",
                )
                result = await ReportTrackerService.update(
                    mock_db, "R-1", update_data
                )
        assert result is mock_tracker
        assert progress[1]["status"] == "rejected"
        assert len(progress) == 3
        assert progress[2]["step_id"] == "unpublish_in_progress"

    def test_accept_inserts_missing_next_step_when_path_resolves_to_step_not_in_tracker(
        self, service
    ):
        """_accept with path that resolves to a step not in tracker inserts it and activates."""
        from unittest.mock import MagicMock
        workflow_json = {
            "steps": [
                {
                    "step_id": "A",
                    "step_name": "Step A",
                    "stage_name": "Review",
                    "transitions": {
                        "success_goto": {"default": "C", "branch": "B"}
                    },
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
                {
                    "step_id": "B",
                    "step_name": "Step B",
                    "stage_name": "Review",
                    "transitions": {"success_goto": "NA"},
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
                {
                    "step_id": "C",
                    "step_name": "Step C",
                    "stage_name": "Review",
                    "transitions": {"success_goto": "NA"},
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
            ]
        }
        steps = [
            {"step_id": "A", "status": "in_progress", "instance_id": "iA"},
            {"step_id": "C", "status": "yet_to_start", "instance_id": "iC"},
        ]
        current_step = steps[0]
        current_step_json = workflow_json["steps"][0]
        tracker = MagicMock()
        ReportTrackerService._accept(
            tracker, steps, current_step, current_step_json, workflow_json, path="branch"
        )
        assert steps[0]["status"] == "completed"
        assert len(steps) == 3
        assert steps[1]["step_id"] == "B"
        assert steps[1]["status"] == "in_progress"
        assert steps[2]["step_id"] == "C"

    def test_accept_duplicate_check_uses_existing_step_when_next_step_already_in_tracker(
        self, service
    ):
        """_accept when resolved next step already exists later in tracker: no insert, use existing."""
        from unittest.mock import MagicMock
        workflow_json = {
            "steps": [
                {
                    "step_id": "A",
                    "step_name": "Step A",
                    "stage_name": "Review",
                    "transitions": {
                        "success_goto": {"default": "C", "branch": "B"}
                    },
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
                {
                    "step_id": "B",
                    "step_name": "Step B",
                    "stage_name": "Review",
                    "transitions": {"success_goto": "NA"},
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
                {
                    "step_id": "C",
                    "step_name": "Step C",
                    "stage_name": "Review",
                    "transitions": {"success_goto": "NA"},
                    "actor": {},
                    "is_optional": False,
                    "sla": {},
                },
            ]
        }
        steps = [
            {"step_id": "A", "status": "in_progress", "instance_id": "iA"},
            {"step_id": "B", "status": "yet_to_start", "instance_id": "iB"},
            {"step_id": "C", "status": "yet_to_start", "instance_id": "iC"},
        ]
        current_step = steps[0]
        current_step_json = workflow_json["steps"][0]
        tracker = MagicMock()
        initial_len = len(steps)
        ReportTrackerService._accept(
            tracker, steps, current_step, current_step_json, workflow_json, path="branch"
        )
        assert len(steps) == initial_len
        assert sum(1 for s in steps if s.get("step_id") == "B") == 1
        assert steps[1]["step_id"] == "B"
        assert steps[1]["status"] == "in_progress"
        assert steps[0]["status"] == "completed"


class TestIsAssigneeActive:
    """Tests for _is_assignee_active helper."""

    def test_active_status(self):
        assert ReportTrackerService._is_assignee_active({"status": "active"}) is True

    def test_inactive_status(self):
        assert ReportTrackerService._is_assignee_active({"status": "inactive"}) is False

    def test_no_status_key_v1_legacy(self):
        assert ReportTrackerService._is_assignee_active({"user_id": "u1"}) is True

    def test_non_dict(self):
        assert ReportTrackerService._is_assignee_active("not-a-dict") is False

    def test_none_value(self):
        assert ReportTrackerService._is_assignee_active(None) is False


class TestAssignUserToStepV2:
    """Tests for assign_user_to_step_v2 service method."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    def _make_tracker(self, progress_tracker):
        tracker = MagicMock()
        tracker.report_id = "R-1"
        tracker.workflow_steps_json = {"progress_tracker": progress_tracker}
        return tracker

    def _make_step(self, instance_id, step_status="yet_to_start"):
        return {
            "instance_id": instance_id,
            "step_id": "draft",
            "step_name": "Initial Draft",
            "stage_name": "Authoring",
            "status": step_status,
            "app_data": {"assignee": []},
        }

    async def _do_assign(self, mock_db, tracker, instance_id, **overrides):
        defaults = dict(
            user_id="u1", user_name="User One",
            user_email="u1@example.com", role="Lead Author",
        )
        defaults.update(overrides)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        with patch(
            "app.services.report_tracker_service.flag_modified",
        ), patch.object(
            ReportTrackerService, "get_by_report_id",
            new_callable=AsyncMock, return_value=tracker,
        ):
            return await ReportTrackerService.assign_user_to_step_v2(
                db=mock_db, report_id="R-1", instance_id=instance_id, **defaults,
            )

    @pytest.mark.asyncio
    async def test_v2_returns_none_tracker_not_found(self, mock_db):
        with patch.object(
            ReportTrackerService, "get_by_report_id",
            new_callable=AsyncMock, return_value=None,
        ):
            result = await ReportTrackerService.assign_user_to_step_v2(
                db=mock_db, report_id="nope", instance_id="x",
                user_id="u1", user_name="User", user_email="u@e.com", role="R",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_v2_raises_instance_id_not_found(self, mock_db):
        from app.exceptions import UnprocessableEntityException
        tracker = self._make_tracker([self._make_step("id-1")])
        with pytest.raises(UnprocessableEntityException):
            await self._do_assign(mock_db, tracker, instance_id="nonexistent")

    @pytest.mark.asyncio
    async def test_v2_raises_progress_tracker_empty(self, mock_db):
        from app.exceptions import UnprocessableEntityException
        tracker = self._make_tracker([])
        with pytest.raises(UnprocessableEntityException):
            await self._do_assign(mock_db, tracker, instance_id="x")

    @pytest.mark.asyncio
    async def test_v2_first_assignment_has_9_keys(self, mock_db):
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assignees = step["app_data"]["assignee"]
        assert len(assignees) == 1
        expected_keys = {
            "user_id", "user_name", "user_email", "role",
            "status", "assigned_at", "started_at", "completed_at", "unassigned_at",
        }
        assert set(assignees[0].keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_v2_status_is_active(self, mock_db):
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_v2_assigned_at_is_utc_iso(self, mock_db):
        from datetime import datetime, timezone
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        ts = step["app_data"]["assignee"][0]["assigned_at"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_v2_started_at_null_on_yet_to_start(self, mock_db):
        step = self._make_step("id-1", step_status="yet_to_start")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["started_at"] is None

    @pytest.mark.asyncio
    async def test_v2_started_at_set_on_in_progress_step(self, mock_db):
        step = self._make_step("id-1", step_status="in_progress")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_v2_started_at_set_on_retry_step(self, mock_db):
        step = self._make_step("id-1", step_status="retry")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_v2_completed_at_null_on_new(self, mock_db):
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["completed_at"] is None

    @pytest.mark.asyncio
    async def test_v2_unassigned_at_null_on_new(self, mock_db):
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["unassigned_at"] is None

    @pytest.mark.asyncio
    async def test_v2_deactivates_existing_active(self, mock_db):
        step = self._make_step("id-1")
        step["app_data"]["assignee"] = [
            {"user_id": "old", "user_name": "Old", "status": "active", "started_at": None,
             "completed_at": None, "unassigned_at": None}
        ]
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        old = step["app_data"]["assignee"][0]
        assert old["status"] == "inactive"
        assert old["unassigned_at"] is not None

    @pytest.mark.asyncio
    async def test_v2_deactivates_multiple_active(self, mock_db):
        step = self._make_step("id-1")
        step["app_data"]["assignee"] = [
            {"user_id": "a", "status": "active"},
            {"user_id": "b", "status": "active"},
        ]
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert step["app_data"]["assignee"][0]["status"] == "inactive"
        assert step["app_data"]["assignee"][1]["status"] == "inactive"
        assert step["app_data"]["assignee"][2]["status"] == "active"

    @pytest.mark.asyncio
    async def test_v2_inactive_untouched(self, mock_db):
        step = self._make_step("id-1")
        step["app_data"]["assignee"] = [
            {"user_id": "old", "status": "inactive", "unassigned_at": "2026-01-01T00:00:00+00:00"}
        ]
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        old = step["app_data"]["assignee"][0]
        assert old["unassigned_at"] == "2026-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_v2_same_person_reassign(self, mock_db):
        step = self._make_step("id-1")
        step["app_data"]["assignee"] = [
            {"user_id": "u1", "user_name": "User One", "status": "active",
             "assigned_at": "2026-01-01", "started_at": None,
             "completed_at": None, "unassigned_at": None}
        ]
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="u1")
        assert len(step["app_data"]["assignee"]) == 2
        assert step["app_data"]["assignee"][0]["status"] == "inactive"
        assert step["app_data"]["assignee"][1]["status"] == "active"

    @pytest.mark.asyncio
    async def test_v2_different_person_reassign(self, mock_db):
        step = self._make_step("id-1")
        step["app_data"]["assignee"] = [
            {"user_id": "u1", "status": "active"}
        ]
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="u2")
        assert step["app_data"]["assignee"][0]["status"] == "inactive"
        assert step["app_data"]["assignee"][1]["user_id"] == "u2"
        assert step["app_data"]["assignee"][1]["status"] == "active"

    @pytest.mark.asyncio
    async def test_v2_history_order_chronological(self, mock_db):
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="u1")
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="u2")
        ids = [a["user_id"] for a in step["app_data"]["assignee"]]
        assert ids == ["u1", "u2"]

    @pytest.mark.asyncio
    async def test_v2_triple_reassign_chain(self, mock_db):
        step = self._make_step("id-1")
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="A")
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="B")
        await self._do_assign(mock_db, tracker, instance_id="id-1", user_id="C")
        statuses = [a["status"] for a in step["app_data"]["assignee"]]
        assert statuses == ["inactive", "inactive", "active"]

    @pytest.mark.asyncio
    async def test_v2_assigns_to_yet_to_start_step(self, mock_db):
        step = self._make_step("id-1", "yet_to_start")
        tracker = self._make_tracker([step])
        result = await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert result is tracker

    @pytest.mark.asyncio
    async def test_v2_assigns_to_in_progress_step(self, mock_db):
        step = self._make_step("id-1", "in_progress")
        tracker = self._make_tracker([step])
        result = await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert result is tracker

    @pytest.mark.asyncio
    async def test_v2_assigns_to_completed_step(self, mock_db):
        step = self._make_step("id-1", "completed")
        tracker = self._make_tracker([step])
        result = await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert result is tracker

    @pytest.mark.asyncio
    async def test_v2_assigns_to_retry_step(self, mock_db):
        step = self._make_step("id-1", "retry")
        tracker = self._make_tracker([step])
        result = await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert result is tracker

    @pytest.mark.asyncio
    async def test_v2_handles_missing_app_data(self, mock_db):
        step = self._make_step("id-1")
        del step["app_data"]
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert len(step["app_data"]["assignee"]) == 1

    @pytest.mark.asyncio
    async def test_v2_handles_assignee_not_list(self, mock_db):
        step = self._make_step("id-1")
        step["app_data"]["assignee"] = "bad_value"
        tracker = self._make_tracker([step])
        await self._do_assign(mock_db, tracker, instance_id="id-1")
        assert isinstance(step["app_data"]["assignee"], list)
        assert len(step["app_data"]["assignee"]) == 1

    @pytest.mark.asyncio
    async def test_v2_handles_missing_workflow_steps_json(self, mock_db):
        from app.exceptions import UnprocessableEntityException
        tracker = MagicMock()
        tracker.report_id = "R-1"
        tracker.workflow_steps_json = None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        with patch(
            "app.services.report_tracker_service.flag_modified",
        ), patch.object(
            ReportTrackerService, "get_by_report_id",
            new_callable=AsyncMock, return_value=tracker,
        ):
            with pytest.raises(UnprocessableEntityException):
                await ReportTrackerService.assign_user_to_step_v2(
                    db=mock_db, report_id="R-1", instance_id="id-1",
                    user_id="u1", user_name="U", user_email="u@e.com", role="R",
                )

    @pytest.mark.asyncio
    async def test_v2_assign_step_a_no_affect_step_b(self, mock_db):
        step_a = self._make_step("id-a")
        step_b = self._make_step("id-b")
        step_b["app_data"]["assignee"] = [{"user_id": "existing", "status": "active"}]
        tracker = self._make_tracker([step_a, step_b])
        await self._do_assign(mock_db, tracker, instance_id="id-a")
        assert len(step_b["app_data"]["assignee"]) == 1
        assert step_b["app_data"]["assignee"][0]["user_id"] == "existing"
        assert step_b["app_data"]["assignee"][0]["status"] == "active"


class TestWorkflowEngineAssigneeTimestamps:
    """Tests for assignee timestamp hooks in _accept/_reject."""

    def test_accept_sets_completed_at_on_active_assignees(self):
        workflow_json = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": "B"}, "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {"success_goto": "NA"}, "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            {"step_id": "A", "status": "in_progress", "instance_id": "iA",
             "app_data": {"assignee": [
                 {"user_id": "u1", "status": "active", "completed_at": None, "started_at": "t0"}
             ]}},
            {"step_id": "B", "status": "yet_to_start", "instance_id": "iB",
             "app_data": {"assignee": []}},
        ]
        tracker = MagicMock()
        ReportTrackerService._accept(
            tracker, steps, steps[0], workflow_json["steps"][0], workflow_json
        )
        assert steps[0]["app_data"]["assignee"][0]["completed_at"] is not None

    def test_accept_sets_started_at_on_next_step_assignees(self):
        workflow_json = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": "B"}, "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {"success_goto": "NA"}, "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            {"step_id": "A", "status": "in_progress", "instance_id": "iA",
             "app_data": {"assignee": [
                 {"user_id": "u1", "status": "active", "completed_at": None, "started_at": "t0"}
             ]}},
            {"step_id": "B", "status": "yet_to_start", "instance_id": "iB",
             "app_data": {"assignee": [
                 {"user_id": "u2", "status": "active", "started_at": None, "completed_at": None}
             ]}},
        ]
        tracker = MagicMock()
        ReportTrackerService._accept(
            tracker, steps, steps[0], workflow_json["steps"][0], workflow_json
        )
        assert steps[1]["app_data"]["assignee"][0]["started_at"] is not None

    def test_accept_skips_inactive_assignees_for_completed_at(self):
        workflow_json = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": "B"}, "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {"success_goto": "NA"}, "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            {"step_id": "A", "status": "in_progress", "instance_id": "iA",
             "app_data": {"assignee": [
                 {"user_id": "old", "status": "inactive", "completed_at": None,
                  "unassigned_at": "2026-01-01T00:00:00+00:00"},
                 {"user_id": "current", "status": "active", "completed_at": None, "started_at": "t0"},
             ]}},
            {"step_id": "B", "status": "yet_to_start", "instance_id": "iB",
             "app_data": {"assignee": []}},
        ]
        tracker = MagicMock()
        ReportTrackerService._accept(
            tracker, steps, steps[0], workflow_json["steps"][0], workflow_json
        )
        assert steps[0]["app_data"]["assignee"][0]["completed_at"] is None
        assert steps[0]["app_data"]["assignee"][1]["completed_at"] is not None

    def test_reject_sets_completed_at_on_active_assignees(self):
        workflow_json = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": "B", "fail_goto": "A"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {"success_goto": "NA"}, "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            {"step_id": "A", "status": "in_progress", "instance_id": "iA",
             "app_data": {"assignee": [
                 {"user_id": "u1", "status": "active", "completed_at": None, "started_at": "t0"}
             ]}},
            {"step_id": "B", "status": "yet_to_start", "instance_id": "iB",
             "app_data": {"assignee": []}},
        ]
        tracker = MagicMock()
        ReportTrackerService._reject(
            tracker, steps, steps[0], workflow_json["steps"][0], workflow_json
        )
        assert steps[0]["app_data"]["assignee"][0]["completed_at"] is not None


class TestGetterHelpers:
    """Tests for _first_active_assignee_name and _role_for_lite with v2 data."""

    def test_first_active_assignee_name_returns_active(self):
        step = {"app_data": {"assignee": [
            {"user_name": "Alice", "status": "active"}
        ]}}
        assert ReportTrackerService._first_active_assignee_name(step) == "Alice"

    def test_first_active_assignee_name_skips_inactive(self):
        step = {"app_data": {"assignee": [
            {"user_name": "Old", "status": "inactive"},
            {"user_name": "New", "status": "active"},
        ]}}
        assert ReportTrackerService._first_active_assignee_name(step) == "New"

    def test_first_active_assignee_name_mixed_list(self):
        step = {"app_data": {"assignee": [
            {"user_name": "X", "status": "inactive"},
            {"user_name": "Y", "status": "inactive"},
            {"user_name": "Z", "status": "active"},
        ]}}
        assert ReportTrackerService._first_active_assignee_name(step) == "Z"

    def test_first_active_assignee_name_all_inactive(self):
        step = {"app_data": {"assignee": [
            {"user_name": "X", "status": "inactive"},
        ]}}
        assert ReportTrackerService._first_active_assignee_name(step) == "Unassigned"

    def test_role_for_lite_returns_active_role(self):
        step = {"app_data": {"assignee": [
            {"role": "Lead Author", "status": "active"}
        ]}}
        assert ReportTrackerService._role_for_lite(step, "Alice") == "Lead Author"

    def test_role_for_lite_skips_inactive(self):
        step = {"app_data": {"assignee": [
            {"role": "Old Role", "status": "inactive"},
            {"role": "New Role", "status": "active"},
        ]}}
        assert ReportTrackerService._role_for_lite(step, "New") == "New Role"
