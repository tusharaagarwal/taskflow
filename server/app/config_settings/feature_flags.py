# TEMP MOCK: Feature flag for CPM API
MOCK_CPM_API_USED = True  # Set to False to use real CPM API

# Default workflow ID — caller reads from DB config at runtime via app_config_service
# and falls back to this if the key is absent or invalid.
DEFAULT_MOCK_WORKFLOW_ID = 1
