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
    async def test_get_current_stage_summary_returns_none_when_tracker_not_found(self, mock_db):
        """get_current_stage_summary returns None when tracker is missing."""
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await ReportTrackerService.get_current_stage_summary(mock_db, "missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_current_stage_summary_returns_current_step_and_lists(self, mock_db):
        """get_current_stage_summary returns current-step-focused lists for in_progress step."""
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-3"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {
                    "instance_id": "i1",
                    "step_id": "draft",
                    "step_name": "Draft",
                    "stage_name": "Authoring",
                    "status": "in_progress",
                    "actor": {"role": "analyst"},
                    "action_available": ["accept", "submit"],
                    "app_data": {
                        "assignee": [
                            {"user_name": "Jane", "role": "Lead Reviewer", "persona_id": 1001, "status": "active"},
                            {"user_name": "Tom", "role": "Lead Reviewer", "persona_id": 1001, "status": "active"},
                            {"user_name": "Old", "role": "Legacy", "status": "inactive"},
                        ],
                        "personas": [4],
                    },
                },
                {
                    "instance_id": "i2",
                    "step_id": "review",
                    "step_name": "Review",
                    "stage_name": "Review",
                    "status": "yet_to_start",
                    "actor": {"role": "reviewer"},
                    "action_available": "invalid_type",
                    "app_data": {"assignee": []},
                },
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_current_stage_summary(mock_db, "R-3")

        assert result is not None
        assert result["report_id"] == "R-3"
        assert result["current_step_name"] == "Draft"
        assert result["current_stage_name"] == "Authoring"
        assert result["steps"] == ["Draft", "Review"]
        assert result["actions_available"] == ["accept", "submit"]
        assert result["persona_id"] == [4]

    @pytest.mark.asyncio
    async def test_get_current_stage_summary_uses_retry_as_current(self, mock_db):
        """retry step is selected as current step when in_progress is absent."""
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-4"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {
                    "instance_id": "i1",
                    "step_id": "review",
                    "step_name": "Review Retry",
                    "stage_name": "Review",
                    "status": "retry",
                    "actor": {"role": "reviewer"},
                    "action_available": [],
                    "app_data": {
                        "assignee": [
                            {"user_name": "Jane", "role": "Lead Reviewer", "persona_id": 1002, "status": "active"}
                        ],
                        "personas": [9],
                    },
                }
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_current_stage_summary(mock_db, "R-4")

        assert result is not None
        assert result["current_step_name"] == "Review Retry"
        assert result["steps"] == ["Review Retry"]
        assert result["persona_id"] == [9]

    @pytest.mark.asyncio
    async def test_get_current_stage_summary_returns_empty_current_lists_without_active_step(self, mock_db):
        """When no in_progress/retry step exists, current-step roles/actions lists are empty."""
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-5"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {
                    "instance_id": "i1",
                    "step_id": "draft",
                    "step_name": "Draft",
                    "stage_name": "Authoring",
                    "status": "completed",
                    "actor": {"role": "analyst"},
                    "action_available": ["accept"],
                    "app_data": {"assignee": []},
                },
                {
                    "instance_id": "i2",
                    "step_id": "approval",
                    "step_name": "",
                    "stage_name": "Approval",
                    "status": "yet_to_start",
                    "actor": {"role": "approver"},
                    "action_available": ["approve"],
                    "app_data": {"assignee": []},
                },
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_current_stage_summary(mock_db, "R-5")

        assert result is not None
        assert result["current_step_name"] is None
        assert result["current_stage_name"] is None
        assert result["steps"] == ["Draft", "approval"]
        assert result["persona_id"] == []
        assert result["actions_available"] == []

    @pytest.mark.asyncio
    async def test_get_current_stage_summary_roles_fallback_to_personas_when_assignee_missing(self, mock_db):
        """Persona IDs are sourced from app_data.personas when assignee persona_id is missing."""
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-6"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {
                    "instance_id": "i1",
                    "step_id": "copy-edit",
                    "step_name": "Copy Edit",
                    "stage_name": "Editing",
                    "status": "in_progress",
                    "actor": {"role": "copy_editor", "persona_id": 101},
                    "action_available": ["submit"],
                    "app_data": {
                        "assignee": [{"user_name": "NoRoleUser", "status": "active"}],
                        "personas": [
                            {"role": "Copy Editor", "persona_id": 2001},
                            {"role": "Copy Editor", "persona_id": 2001},
                        ],
                    },
                }
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_current_stage_summary(mock_db, "R-6")

        assert result is not None
        assert result["persona_id"] == [2001]

    @pytest.mark.asyncio
    async def test_get_current_stage_summary_ignores_assignee_actor_persona_ids_when_personas_missing(self, mock_db):
        """assignee/actor persona_id values are ignored when app_data.personas is absent."""
        mock_tracker = MagicMock()
        mock_tracker.report_id = "R-7"
        mock_tracker.workflow_steps_json = {
            "progress_tracker": [
                {
                    "instance_id": "i1",
                    "step_id": "copy-edit",
                    "step_name": "Copy Edit",
                    "stage_name": "Editing",
                    "status": "in_progress",
                    "actor": {"role": "copy_editor", "persona_id": 9999},
                    "action_available": ["submit"],
                    "app_data": {
                        "assignee": [
                            {"user_name": "Rakesh", "role": "Copy Editor", "persona_id": 8888, "status": "active"}
                        ]
                    },
                }
            ]
        }
        with patch.object(
            ReportTrackerService,
            "get_by_report_id",
            new_callable=AsyncMock,
            return_value=mock_tracker,
        ):
            result = await ReportTrackerService.get_current_stage_summary(mock_db, "R-7")

        assert result is not None
        assert result["persona_id"] == []

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


class TestCloneStepInstance:
    """Tests for _clone_step_instance helper."""

    def test_clone_preserves_app_data_and_resets_assignee_timestamps(self):
        source = {
            "instance_id": "original-id",
            "step_id": "draft",
            "step_name": "Initial Draft",
            "stage_name": "Authoring",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-02T00:00:00Z",
            "app_data": {
                "assignee": [
                    {"user_id": "u1", "user_name": "Alice", "role": "Lead Author",
                     "status": "active",
                     "assigned_at": "2026-01-01T00:00:00Z",
                     "started_at": "2026-01-01T01:00:00Z",
                     "completed_at": "2026-01-02T00:00:00Z",
                     "unassigned_at": None},
                    {"user_id": "u0", "user_name": "Bob", "role": "Author",
                     "status": "inactive",
                     "assigned_at": "2025-12-20T00:00:00Z",
                     "started_at": "2025-12-20T01:00:00Z",
                     "completed_at": None,
                     "unassigned_at": "2025-12-31T00:00:00Z"},
                ],
                "personas": [101, 102],
                "custom_analytics": {"views": 42},
            },
            "actor": {"role": "analyst"},
            "sla": {"hours": 24},
        }
        clone = ReportTrackerService._clone_step_instance(source, status="in_progress")

        assert clone["instance_id"] != "original-id"
        assert clone["status"] == "in_progress"
        assert clone["started_at"] is None
        assert clone["completed_at"] is None
        assert clone["step_id"] == "draft"
        assert clone["app_data"]["custom_analytics"]["views"] == 42
        assert clone["sla"] == {"hours": 24}

        alice = clone["app_data"]["assignee"][0]
        assert alice["user_id"] == "u1"
        assert alice["status"] == "active"
        assert alice["assigned_at"] == "2026-01-01T00:00:00Z"
        assert alice["started_at"] is None
        assert alice["completed_at"] is None
        assert alice["unassigned_at"] is None

        bob = clone["app_data"]["assignee"][1]
        assert bob["status"] == "inactive"
        assert bob["assigned_at"] == "2025-12-20T00:00:00Z"
        assert bob["started_at"] is None
        assert bob["completed_at"] is None
        assert bob["unassigned_at"] == "2025-12-31T00:00:00Z"

    def test_clone_is_deep_copy(self):
        source = {
            "instance_id": "orig",
            "status": "completed",
            "started_at": "t0",
            "completed_at": "t1",
            "app_data": {"assignee": [{"user_id": "u1"}]},
        }
        clone = ReportTrackerService._clone_step_instance(source)
        clone["app_data"]["assignee"].append({"user_id": "u2"})

        assert len(source["app_data"]["assignee"]) == 1

    def test_clone_default_status_is_yet_to_start(self):
        source = {"instance_id": "x", "status": "completed", "started_at": "t0", "completed_at": "t1"}
        clone = ReportTrackerService._clone_step_instance(source)
        assert clone["status"] == "yet_to_start"


class TestFindLatestInstanceByStepId:
    """Tests for _find_latest_instance_by_step_id helper."""

    def test_finds_latest_instance(self):
        steps = [
            {"step_id": "A", "instance_id": "A1", "app_data": {"v": 1}},
            {"step_id": "B", "instance_id": "B1"},
            {"step_id": "A", "instance_id": "A2", "app_data": {"v": 2}},
            {"step_id": "C", "instance_id": "C1"},
        ]
        result = ReportTrackerService._find_latest_instance_by_step_id(steps, "A", up_to_index=3)
        assert result["instance_id"] == "A2"
        assert result["app_data"]["v"] == 2

    def test_respects_up_to_index_boundary(self):
        steps = [
            {"step_id": "A", "instance_id": "A1"},
            {"step_id": "B", "instance_id": "B1"},
            {"step_id": "A", "instance_id": "A2"},
        ]
        result = ReportTrackerService._find_latest_instance_by_step_id(steps, "A", up_to_index=1)
        assert result["instance_id"] == "A1"

    def test_returns_none_when_not_found(self):
        steps = [{"step_id": "B", "instance_id": "B1"}]
        result = ReportTrackerService._find_latest_instance_by_step_id(steps, "A", up_to_index=0)
        assert result is None

    def test_empty_steps(self):
        result = ReportTrackerService._find_latest_instance_by_step_id([], "A", up_to_index=-1)
        assert result is None


class TestNormalRejectionFlowPreservesData:
    """Tests for the clone-based normal rejection flow in _reject."""

    @staticmethod
    def _make_workflow(*step_defs):
        steps = []
        for i, sd in enumerate(step_defs):
            step = {
                "step_id": sd["id"],
                "step_name": sd.get("name", sd["id"]),
                "stage_name": sd.get("stage", "Stage"),
                "transitions": {
                    "success_goto": sd.get("success_goto", "NA"),
                    "fail_goto": sd.get("fail_goto", "NA"),
                },
                "actor": sd.get("actor", {}),
                "is_optional": False,
                "sla": {},
            }
            steps.append(step)
        return {"steps": steps}

    @staticmethod
    def _make_step_instance(step_id, status, instance_id=None, app_data=None, **extra):
        inst = {
            "instance_id": instance_id or f"inst-{step_id}",
            "step_id": step_id,
            "step_name": step_id,
            "stage_name": "Stage",
            "status": status,
            "started_at": "2026-01-01T00:00:00Z" if status != "yet_to_start" else None,
            "completed_at": "2026-01-02T00:00:00Z" if status == "completed" else None,
            "actor": {},
            "is_optional": False,
            "sla": {},
            "action_available": [],
            "app_data": app_data or {"assignee": [], "personas": []},
        }
        inst.update(extra)
        return inst

    def test_reject_preserves_assignee_data(self):
        """Core test: rejection clones existing instances, preserving assignees."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B", "fail_goto": "NA"},
            {"id": "B", "success_goto": "C", "fail_goto": "A"},
            {"id": "C", "success_goto": "NA", "fail_goto": "NA"},
        )
        assignee_data = {
            "assignee": [
                {"user_id": "u1", "user_name": "Alice", "role": "Lead", "status": "active",
                 "started_at": "t0", "completed_at": "t1"}
            ],
            "personas": [101],
            "custom_field": "preserved",
        }
        steps = [
            self._make_step_instance("A", "completed", app_data=assignee_data),
            self._make_step_instance("B", "in_progress", app_data={
                "assignee": [{"user_id": "u2", "status": "active"}], "personas": [102]
            }),
            self._make_step_instance("C", "yet_to_start", app_data={
                "assignee": [{"user_id": "u3", "status": "active"}], "personas": [103]
            }),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        assert steps[1]["status"] == "rejected"

        cloned_a = steps[2]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["status"] == "in_progress"
        assert cloned_a["instance_id"] != steps[0]["instance_id"]
        assert cloned_a["app_data"]["assignee"][0]["user_id"] == "u1"
        assert cloned_a["app_data"]["custom_field"] == "preserved"

        cloned_b = steps[3]
        assert cloned_b["step_id"] == "B"
        assert cloned_b["status"] == "yet_to_start"
        assert cloned_b["instance_id"] != steps[1]["instance_id"]
        assert cloned_b["app_data"]["assignee"][0]["user_id"] == "u2"

        preserved_c = steps[4]
        assert preserved_c["step_id"] == "C"
        assert preserved_c["status"] == "yet_to_start"
        assert preserved_c["app_data"]["assignee"][0]["user_id"] == "u3"

    def test_reject_preserves_forward_steps_data(self):
        """Forward yet_to_start steps with pre-assigned data are cloned with data preserved."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C", "fail_goto": "A"},
            {"id": "C", "success_goto": "D"},
            {"id": "D", "success_goto": "NA"},
        )
        forward_app_data = {
            "assignee": [{"user_id": "pre-assigned", "status": "active"}],
            "personas": [999],
        }
        steps = [
            self._make_step_instance("A", "completed"),
            self._make_step_instance("B", "in_progress"),
            self._make_step_instance("C", "yet_to_start", app_data=forward_app_data),
            self._make_step_instance("D", "yet_to_start", app_data={
                "assignee": [{"user_id": "d-user"}], "personas": [888]
            }),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        assert len(steps) == 6
        assert steps[2]["step_id"] == "A"
        assert steps[2]["status"] == "in_progress"
        assert steps[3]["step_id"] == "B"
        assert steps[3]["status"] == "yet_to_start"
        cloned_c = steps[4]
        assert cloned_c["step_id"] == "C"
        assert cloned_c["app_data"]["assignee"][0]["user_id"] == "pre-assigned"
        assert cloned_c["instance_id"] != "inst-C"
        cloned_d = steps[5]
        assert cloned_d["step_id"] == "D"
        assert cloned_d["app_data"]["assignee"][0]["user_id"] == "d-user"
        assert cloned_d["instance_id"] != "inst-D"

    def test_reject_clones_use_latest_instance(self):
        """When a step has been visited multiple times, the latest instance is used as clone source."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C", "fail_goto": "A"},
            {"id": "C", "success_goto": "NA", "fail_goto": "A"},
        )
        steps = [
            self._make_step_instance("A", "completed", instance_id="A-v1",
                                     app_data={"assignee": [{"user_id": "old"}], "personas": []}),
            self._make_step_instance("B", "completed", instance_id="B-v1"),
            self._make_step_instance("A", "completed", instance_id="A-v2",
                                     app_data={"assignee": [{"user_id": "latest"}], "personas": []}),
            self._make_step_instance("B", "completed", instance_id="B-v2"),
            self._make_step_instance("C", "in_progress", instance_id="C-v1"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[4], workflow["steps"][2], workflow
        )

        cloned_a = steps[5]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["app_data"]["assignee"][0]["user_id"] == "latest"

    def test_reject_no_forward_steps(self):
        """Rejection when rejected step is the last step (no forward steps to preserve)."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "NA", "fail_goto": "A"},
        )
        steps = [
            self._make_step_instance("A", "completed"),
            self._make_step_instance("B", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        assert len(steps) == 4
        assert steps[1]["status"] == "rejected"
        assert steps[2]["step_id"] == "A"
        assert steps[2]["status"] == "in_progress"
        assert steps[3]["step_id"] == "B"
        assert steps[3]["status"] == "yet_to_start"

    def test_reject_multi_step_jump_back(self):
        """Rejection jumping back multiple steps (e.g., Step D -> Step A)."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C"},
            {"id": "C", "success_goto": "D"},
            {"id": "D", "success_goto": "NA", "fail_goto": "A"},
        )
        a_data = {"assignee": [{"user_id": "author"}], "personas": [10]}
        b_data = {"assignee": [{"user_id": "reviewer"}], "personas": [20]}
        c_data = {"assignee": [{"user_id": "editor"}], "personas": [30]}
        steps = [
            self._make_step_instance("A", "completed", app_data=a_data),
            self._make_step_instance("B", "completed", app_data=b_data),
            self._make_step_instance("C", "completed", app_data=c_data),
            self._make_step_instance("D", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[3], workflow["steps"][3], workflow
        )

        assert steps[3]["status"] == "rejected"
        assert len(steps) == 8
        assert steps[4]["step_id"] == "A"
        assert steps[4]["status"] == "in_progress"
        assert steps[4]["app_data"]["assignee"][0]["user_id"] == "author"
        assert steps[5]["step_id"] == "B"
        assert steps[5]["status"] == "yet_to_start"
        assert steps[5]["app_data"]["assignee"][0]["user_id"] == "reviewer"
        assert steps[6]["step_id"] == "C"
        assert steps[6]["status"] == "yet_to_start"
        assert steps[6]["app_data"]["assignee"][0]["user_id"] == "editor"
        assert steps[7]["step_id"] == "D"
        assert steps[7]["status"] == "yet_to_start"

    def test_reject_clone_resets_temporal_fields(self):
        """Cloned steps have fresh instance_ids and reset started_at/completed_at."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "NA", "fail_goto": "A"},
        )
        steps = [
            self._make_step_instance("A", "completed"),
            self._make_step_instance("B", "in_progress"),
        ]
        original_a_instance = steps[0]["instance_id"]
        original_b_instance = steps[1]["instance_id"]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        cloned_a = steps[2]
        cloned_b = steps[3]
        assert cloned_a["instance_id"] != original_a_instance
        assert cloned_b["instance_id"] != original_b_instance
        assert cloned_b["started_at"] is None
        assert cloned_b["completed_at"] is None

    def test_reject_fallback_to_create_for_unvisited_step(self):
        """If a step in the rejection chain was never visited, falls back to _create_step_object."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C", "fail_goto": "A"},
            {"id": "C", "success_goto": "NA"},
        )
        steps = [
            self._make_step_instance("B", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[0], workflow["steps"][1], workflow
        )

        assert steps[0]["status"] == "rejected"
        cloned_a = steps[1]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["status"] == "in_progress"
        assert cloned_a["app_data"]["assignee"] == []

    def test_reject_auto_complete_first_step(self):
        """If fail_goto points to an auto-complete stage, it gets completed immediately."""
        workflow = {
            "steps": [
                {"step_id": "pub", "step_name": "Published", "stage_name": "Published",
                 "transitions": {"success_goto": "review"}, "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "review", "step_name": "Review", "stage_name": "Review",
                 "transitions": {"success_goto": "NA", "fail_goto": "pub"},
                 "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            self._make_step_instance("pub", "completed", stage_name="Published"),
            self._make_step_instance("review", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        cloned_pub = steps[2]
        assert cloned_pub["step_id"] == "pub"
        assert cloned_pub["status"] == "completed"
        assert cloned_pub["completed_at"] is not None

    def test_reject_does_not_mutate_original_steps(self):
        """Cloning must not mutate the original step instances' app_data."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "NA", "fail_goto": "A"},
        )
        original_app_data = {
            "assignee": [{"user_id": "u1", "status": "active"}],
            "personas": [101],
        }
        steps = [
            self._make_step_instance("A", "completed", app_data=original_app_data),
            self._make_step_instance("B", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        cloned_a = steps[2]
        cloned_a["app_data"]["assignee"].append({"user_id": "u2"})
        assert len(steps[0]["app_data"]["assignee"]) == 1

    def test_reject_with_path_resolving_to_different_step(self):
        """Rejection with path parameter resolving fail_goto to a specific step."""
        workflow = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": "B"}, "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {
                     "success_goto": "NA",
                     "fail_goto": {"default": "A", "special": "A"},
                 },
                 "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            self._make_step_instance("A", "completed", app_data={
                "assignee": [{"user_id": "preserved-user"}], "personas": []
            }),
            self._make_step_instance("B", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow, path="special"
        )

        assert steps[1]["status"] == "rejected"
        assert steps[2]["step_id"] == "A"
        assert steps[2]["app_data"]["assignee"][0]["user_id"] == "preserved-user"

    def test_reject_follows_default_chain_not_old_branch(self):
        """When a branching success_goto was previously taken (X instead of default B),
        rejection follows the DEFAULT chain A -> B -> C, not the old A -> X -> C.
        B is created fresh (never visited), A and C preserve their data."""
        workflow = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": {"default": "B", "branch": "X"}},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {"success_goto": "C"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "X", "step_name": "X", "stage_name": "S",
                 "transitions": {"success_goto": "C"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "C", "step_name": "C", "stage_name": "S",
                 "transitions": {"success_goto": "NA", "fail_goto": "A"},
                 "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        steps = [
            self._make_step_instance("A", "completed", app_data={
                "assignee": [{"user_id": "author"}], "personas": [10]
            }),
            self._make_step_instance("X", "completed", app_data={
                "assignee": [{"user_id": "branch-user"}], "personas": [777],
                "branch_analytics": {"score": 99},
            }),
            self._make_step_instance("C", "in_progress", app_data={
                "assignee": [{"user_id": "carol"}], "personas": [30]
            }),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[2], workflow["steps"][3], workflow
        )

        assert steps[2]["status"] == "rejected"
        assert len(steps) == 6
        cloned_a = steps[3]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["status"] == "in_progress"
        assert cloned_a["app_data"]["assignee"][0]["user_id"] == "author"
        cloned_b = steps[4]
        assert cloned_b["step_id"] == "B"
        assert cloned_b["status"] == "yet_to_start"
        assert cloned_b["app_data"]["assignee"] == []
        cloned_c = steps[5]
        assert cloned_c["step_id"] == "C"
        assert cloned_c["status"] == "yet_to_start"
        assert cloned_c["app_data"]["assignee"][0]["user_id"] == "carol"

    def test_reject_complex_fail_goto_dict_with_path(self):
        """Rejection where fail_goto is a complex dict resolved via path parameter,
        and the target step exists in tracker history."""
        workflow = {
            "steps": [
                {"step_id": "draft", "step_name": "Draft", "stage_name": "Authoring",
                 "transitions": {"success_goto": "review"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "review", "step_name": "Review", "stage_name": "Review",
                 "transitions": {"success_goto": "approval"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "approval", "step_name": "Approval", "stage_name": "Approval",
                 "transitions": {
                     "success_goto": "NA",
                     "fail_goto": {"default": "review", "major_revision": "draft"},
                 },
                 "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        draft_data = {
            "assignee": [{"user_id": "author1", "status": "active"}],
            "personas": [1], "notes": "important draft notes",
        }
        review_data = {
            "assignee": [{"user_id": "reviewer1", "status": "active"}],
            "personas": [2], "review_comments": ["fix typo"],
        }
        steps = [
            self._make_step_instance("draft", "completed", app_data=draft_data),
            self._make_step_instance("review", "completed", app_data=review_data),
            self._make_step_instance("approval", "in_progress", app_data={
                "assignee": [{"user_id": "approver1"}], "personas": [3]
            }),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[2], workflow["steps"][2], workflow, path="major_revision"
        )

        assert steps[2]["status"] == "rejected"
        assert len(steps) == 6
        cloned_draft = steps[3]
        assert cloned_draft["step_id"] == "draft"
        assert cloned_draft["status"] == "in_progress"
        assert cloned_draft["app_data"]["notes"] == "important draft notes"
        assert cloned_draft["app_data"]["assignee"][0]["user_id"] == "author1"
        cloned_review = steps[4]
        assert cloned_review["step_id"] == "review"
        assert cloned_review["app_data"]["review_comments"] == ["fix typo"]
        cloned_approval = steps[5]
        assert cloned_approval["step_id"] == "approval"
        assert cloned_approval["status"] == "yet_to_start"

    def test_reject_after_multiple_rejections_uses_latest_path(self):
        """After multiple reject cycles, the latest traversal path is cloned."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C", "fail_goto": "A"},
            {"id": "C", "success_goto": "NA", "fail_goto": "A"},
        )
        steps = [
            self._make_step_instance("A", "completed", instance_id="A-v1",
                                     app_data={"assignee": [{"user_id": "old-author"}], "personas": []}),
            self._make_step_instance("B", "rejected", instance_id="B-v1"),
            self._make_step_instance("A", "completed", instance_id="A-v2",
                                     app_data={"assignee": [{"user_id": "new-author"}], "personas": [],
                                               "revision_count": 2}),
            self._make_step_instance("B", "completed", instance_id="B-v2",
                                     app_data={"assignee": [{"user_id": "reviewer-v2"}], "personas": []}),
            self._make_step_instance("C", "in_progress", instance_id="C-v1"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[4], workflow["steps"][2], workflow
        )

        assert steps[4]["status"] == "rejected"
        cloned_a = steps[5]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["app_data"]["assignee"][0]["user_id"] == "new-author"
        assert cloned_a["app_data"]["revision_count"] == 2
        cloned_b = steps[6]
        assert cloned_b["step_id"] == "B"
        assert cloned_b["app_data"]["assignee"][0]["user_id"] == "reviewer-v2"

    def test_reject_to_unvisited_step_falls_back_to_workflow_json(self):
        """When fail_goto points to a step never visited, falls back to workflow JSON chain."""
        workflow = self._make_workflow(
            {"id": "X", "success_goto": "B"},
            {"id": "B", "success_goto": "NA", "fail_goto": "X"},
        )
        steps = [
            self._make_step_instance("B", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[0], workflow["steps"][1], workflow
        )

        assert steps[0]["status"] == "rejected"
        cloned_x = steps[1]
        assert cloned_x["step_id"] == "X"
        assert cloned_x["status"] == "in_progress"
        cloned_b = steps[2]
        assert cloned_b["step_id"] == "B"
        assert cloned_b["status"] == "yet_to_start"

    def test_reject_preserves_skipped_step_data_in_default_chain(self):
        """A previously skipped step's data (e.g. skip_reason) is preserved
        when it appears in the default chain during rejection."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C"},
            {"id": "C", "success_goto": "D"},
            {"id": "D", "success_goto": "NA", "fail_goto": "A"},
        )
        steps = [
            self._make_step_instance("A", "completed", app_data={
                "assignee": [{"user_id": "u-a"}], "personas": []}),
            self._make_step_instance("B", "skipped", app_data={
                "assignee": [], "personas": [], "skip_reason": "optional"}),
            self._make_step_instance("C", "completed", app_data={
                "assignee": [{"user_id": "u-c"}], "personas": []}),
            self._make_step_instance("D", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[3], workflow["steps"][3], workflow
        )

        assert len(steps) == 8
        assert steps[4]["step_id"] == "A"
        assert steps[4]["status"] == "in_progress"
        assert steps[5]["step_id"] == "B"
        assert steps[5]["status"] == "yet_to_start"
        assert steps[5]["app_data"]["skip_reason"] == "optional"
        assert steps[6]["step_id"] == "C"
        assert steps[6]["status"] == "yet_to_start"
        assert steps[7]["step_id"] == "D"
        assert steps[7]["status"] == "yet_to_start"

    def test_reject_branching_step_visited_in_earlier_cycle_preserves_data(self):
        """B was visited in an earlier cycle via the default path, then the user
        took a branch path (X) in a later cycle.  On rejection, the default chain
        includes B, and B's accumulated data from its earlier visit is preserved."""
        workflow = {
            "steps": [
                {"step_id": "A", "step_name": "A", "stage_name": "S",
                 "transitions": {"success_goto": {"default": "B", "branch": "X"}},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "B", "step_name": "B", "stage_name": "S",
                 "transitions": {"success_goto": "C"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "X", "step_name": "X", "stage_name": "S",
                 "transitions": {"success_goto": "C"},
                 "actor": {}, "is_optional": False, "sla": {}},
                {"step_id": "C", "step_name": "C", "stage_name": "S",
                 "transitions": {"success_goto": "NA", "fail_goto": "A"},
                 "actor": {}, "is_optional": False, "sla": {}},
            ]
        }
        b_data = {
            "assignee": [{"user_id": "b-reviewer", "status": "active"}],
            "personas": [200], "review_score": 85,
        }
        steps = [
            self._make_step_instance("A", "completed", instance_id="A-v1"),
            self._make_step_instance("B", "completed", instance_id="B-v1", app_data=b_data),
            self._make_step_instance("C", "rejected", instance_id="C-v1"),
            self._make_step_instance("A", "completed", instance_id="A-v2",
                                     app_data={"assignee": [{"user_id": "author-v2"}], "personas": []}),
            self._make_step_instance("X", "completed", instance_id="X-v1",
                                     app_data={"assignee": [{"user_id": "branch-user"}], "personas": []}),
            self._make_step_instance("C", "in_progress", instance_id="C-v2",
                                     app_data={"assignee": [{"user_id": "carol-v2"}], "personas": []}),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[5], workflow["steps"][3], workflow
        )

        assert steps[5]["status"] == "rejected"
        cloned_a = steps[6]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["status"] == "in_progress"
        assert cloned_a["app_data"]["assignee"][0]["user_id"] == "author-v2"
        cloned_b = steps[7]
        assert cloned_b["step_id"] == "B"
        assert cloned_b["status"] == "yet_to_start"
        assert cloned_b["app_data"]["assignee"][0]["user_id"] == "b-reviewer"
        assert cloned_b["app_data"]["review_score"] == 85
        cloned_c = steps[8]
        assert cloned_c["step_id"] == "C"
        assert cloned_c["status"] == "yet_to_start"
        assert cloned_c["app_data"]["assignee"][0]["user_id"] == "carol-v2"

    def test_reject_forward_yet_to_start_step_with_preassigned_user(self):
        """A yet_to_start forward step (C) has a user pre-assigned via
        assign_user_to_step_v2 before it was ever reached.  On rejection from B
        back to A, C's pre-assigned data is preserved in the rebuilt chain."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "C", "fail_goto": "A"},
            {"id": "C", "success_goto": "NA"},
        )
        steps = [
            self._make_step_instance("A", "completed", app_data={
                "assignee": [{"user_id": "alice"}], "personas": [1]
            }),
            self._make_step_instance("B", "in_progress"),
            self._make_step_instance("C", "yet_to_start", app_data={
                "assignee": [
                    {"user_id": "eve-preassigned", "user_name": "Eve",
                     "role": "Reviewer", "status": "active",
                     "assigned_at": "2026-01-15T00:00:00Z", "started_at": None,
                     "completed_at": None, "unassigned_at": None}
                ],
                "personas": [42],
            }),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        assert steps[1]["status"] == "rejected"
        assert len(steps) == 5
        cloned_a = steps[2]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["status"] == "in_progress"
        assert cloned_a["app_data"]["assignee"][0]["user_id"] == "alice"
        cloned_b = steps[3]
        assert cloned_b["step_id"] == "B"
        assert cloned_b["status"] == "yet_to_start"
        cloned_c = steps[4]
        assert cloned_c["step_id"] == "C"
        assert cloned_c["status"] == "yet_to_start"
        assert cloned_c["app_data"]["assignee"][0]["user_id"] == "eve-preassigned"
        assert cloned_c["app_data"]["assignee"][0]["role"] == "Reviewer"
        assert cloned_c["app_data"]["personas"] == [42]

    def test_reject_cloned_in_progress_step_gets_fresh_assignee_timestamps(self):
        """The first cloned step (set to in_progress) should have its assignee
        started_at set to current_time via _set_assignee_timestamps_on_activation,
        and completed_at should be None.  Stale values from the source must not
        carry over."""
        workflow = self._make_workflow(
            {"id": "A", "success_goto": "B"},
            {"id": "B", "success_goto": "NA", "fail_goto": "A"},
        )
        steps = [
            self._make_step_instance("A", "completed", app_data={
                "assignee": [
                    {"user_id": "u1", "user_name": "Alice", "role": "Lead",
                     "status": "active",
                     "assigned_at": "2026-01-01T00:00:00Z",
                     "started_at": "2026-01-01T01:00:00Z",
                     "completed_at": "2026-01-02T00:00:00Z",
                     "unassigned_at": None}
                ],
                "personas": [1],
            }),
            self._make_step_instance("B", "in_progress"),
        ]
        tracker = MagicMock()

        ReportTrackerService._reject(
            tracker, steps, steps[1], workflow["steps"][1], workflow
        )

        cloned_a = steps[2]
        assert cloned_a["step_id"] == "A"
        assert cloned_a["status"] == "in_progress"
        assert cloned_a["started_at"] is not None

        alice = cloned_a["app_data"]["assignee"][0]
        assert alice["user_id"] == "u1"
        assert alice["assigned_at"] == "2026-01-01T00:00:00Z"
        assert alice["started_at"] is not None
        assert alice["started_at"] != "2026-01-01T01:00:00Z"
        assert alice["completed_at"] is None
        assert alice["unassigned_at"] is None

        cloned_b = steps[3]
        assert cloned_b["status"] == "yet_to_start"
        b_assignees = cloned_b["app_data"].get("assignee", [])
        for assignee in b_assignees:
            assert assignee.get("started_at") is None
            assert assignee.get("completed_at") is None
