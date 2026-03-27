"""Hardcoded fallbacks when a runtime config key is missing or invalid in DB."""

from app.config_settings.feature_flags import DEFAULT_MOCK_WORKFLOW_ID

# Same default as mock CPM / local dev; DB `data.default_workflow_id` overrides when set.
DEFAULT_WORKFLOW_ID_CODE_FALLBACK: int | None = DEFAULT_MOCK_WORKFLOW_ID
