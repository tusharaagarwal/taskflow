# ============================================================
# Workflow API Agent
# Agent that calls the Report Tracker REST APIs
# Features:
# - Retry logic (up to 3 times) for API calls
# - Alert notification on repeated failures
# - Timestamped log files for each run
# ============================================================

try:
    from langchain_openai import AzureChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_core.tools import tool
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError as e:
    print(f"⚠️ Failed to import LangChain modules: {e}")
    print("⚠️ Running in rule-based mode only")
    
    # Mock required classes to prevent NameErrors later
    class AzureChatOpenAI: pass
    class ChatAnthropic: pass
    
    # Mock tool decorator if missing
    def tool(func): return func
    
    # Mock message classes
    class HumanMessage:
        def __init__(self, content): self.content = content
    class SystemMessage:
        def __init__(self, content): self.content = content
import json
import os
import sys
import httpx
import logging
import time
from pathlib import Path
from typing import Optional, Callable, Any
from datetime import datetime, timezone
from functools import wraps
from dotenv import load_dotenv

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))
from app.constants import WorkflowActionType

# ============================================================
# Configuration
# ============================================================

# Load environment variables from .env or .env_dev file
env_path = Path(__file__).parent / ".env"
env_dev_path = Path(__file__).parent / ".env_dev"

if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment from: {env_path}")
elif env_dev_path.exists():
    load_dotenv(env_dev_path)
    print(f"✅ Loaded environment from: {env_dev_path}")
else:
    print("⚠️ No .env or .env_dev file found")

# API Base URL - change this to your server URL
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8003/v1")

# Azure OpenAI Configuration - loaded from environment variables
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")

# Anthropic/Claude Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
USE_ANTHROPIC = os.getenv("USE_ANTHROPIC", "false").lower() == "true"

# Set to True to use mock mode (no actual API calls)
USE_MOCK_MODE = os.getenv("USE_MOCK_MODE", "false").lower() == "true"

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1  # Delay between retries

# ============================================================
# Logging Setup - Timestamped Log File
# ============================================================

# Create logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Generate timestamped log filename
RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILENAME = LOGS_DIR / f"api_agent_{RUN_TIMESTAMP}.log"

# Configure logging with both console and file handlers
logger = logging.getLogger("api_agent")
logger.setLevel(logging.INFO)

# Clear any existing handlers
logger.handlers = []

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File handler with timestamp
file_handler = logging.FileHandler(LOG_FILENAME, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

logger.info(f"=== API Agent Session Started ===")
logger.info(f"Log file: {LOG_FILENAME}")


# ============================================================
# Alert System (Mock)
# ============================================================

def send_alert(alert_type: str, message: str, details: dict = None) -> dict:
    """
    Mock alert function - sends an alert when API fails after max retries.
    In production, this would integrate with:
    - Email notifications
    - Slack/Teams webhooks
    - PagerDuty
    - AWS SNS
    - etc.
    """
    alert_data = {
        "alert_id": f"ALERT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": alert_type,
        "message": message,
        "details": details or {},
        "severity": "HIGH" if "failed" in message.lower() else "MEDIUM"
    }
    
    logger.warning("="*60)
    logger.warning(f"🚨 ALERT TRIGGERED: {alert_type}")
    logger.warning(f"   Message: {message}")
    logger.warning(f"   Alert ID: {alert_data['alert_id']}")
    logger.warning(f"   Severity: {alert_data['severity']}")
    if details:
        logger.warning(f"   Details: {json.dumps(details, indent=2)}")
    logger.warning("="*60)
    
    # In production, you would send this to your alerting system
    # Example: send_to_slack(alert_data), send_email(alert_data), etc.
    
    return alert_data


# ============================================================
# Retry Logic
# ============================================================

def api_call_with_retry(
    func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY_SECONDS,
    operation_name: str = "API call",
    **kwargs
) -> dict:
    """
    Execute an API call with retry logic.
    
    Args:
        func: The function to call
        *args: Positional arguments for the function
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        operation_name: Name of the operation for logging
        **kwargs: Keyword arguments for the function
    
    Returns:
        dict: Result from the function or error with alert
    """
    last_exception = None
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[RETRY] Attempt {attempt}/{max_retries} for {operation_name}")
            result = func(*args, **kwargs)
            
            # Check if result indicates success
            if isinstance(result, dict) and result.get("status") == "error":
                # API returned an error response, but connection succeeded
                # Only retry on connection/timeout errors, not on business logic errors
                if "HTTP error" in result.get("message", "") or "Error:" in result.get("message", ""):
                    raise Exception(result.get("message"))
                else:
                    # Business logic error, don't retry
                    return result
            
            logger.info(f"[RETRY] {operation_name} succeeded on attempt {attempt}")
            return result
            
        except httpx.ConnectError as e:
            last_exception = e
            logger.warning(f"[RETRY] Connection error on attempt {attempt}: {e}")
        except httpx.TimeoutException as e:
            last_exception = e
            logger.warning(f"[RETRY] Timeout on attempt {attempt}: {e}")
        except httpx.HTTPStatusError as e:
            # Only retry on 5xx errors (server errors)
            if e.response.status_code >= 500:
                last_exception = e
                logger.warning(f"[RETRY] Server error {e.response.status_code} on attempt {attempt}")
            else:
                # 4xx errors are client errors, don't retry
                logger.error(f"[RETRY] Client error {e.response.status_code}, not retrying")
                raise
        except Exception as e:
            last_exception = e
            logger.warning(f"[RETRY] Error on attempt {attempt}: {e}")
        
        if attempt < max_retries:
            logger.info(f"[RETRY] Waiting {retry_delay}s before retry...")
            time.sleep(retry_delay)
    
    # All retries exhausted - send alert
    error_message = f"{operation_name} failed after {max_retries} attempts"
    alert = send_alert(
        alert_type="API_FAILURE",
        message=error_message,
        details={
            "operation": operation_name,
            "max_retries": max_retries,
            "last_error": str(last_exception),
            "api_base_url": API_BASE_URL
        }
    )
    
    return {
        "status": "error",
        "message": error_message,
        "last_error": str(last_exception),
        "alert": alert
    }


# ============================================================
# HTTP Client
# ============================================================

def get_http_client():
    """Get HTTP client for API calls"""
    return httpx.Client(base_url=API_BASE_URL, timeout=30.0)


# ============================================================
# Internal API Functions (with retry support)
# ============================================================

def _list_report_trackers_internal() -> dict:
    """Internal function to list report trackers"""
    with get_http_client() as client:
        response = client.get("/report-tracker/")
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Listed {len(data)} report trackers"
        }


def _create_report_tracker_internal(report_id: str, content_product_name: str) -> dict:
    """Internal function to create report tracker"""
    with get_http_client() as client:
        response = client.post(
            "/report-tracker/",
            json={
                "report_id": report_id,
                "content_product_name": content_product_name
            }
        )
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Created report tracker '{report_id}'"
        }


def _get_report_tracker_internal(report_id: str) -> dict:
    """Internal function to get report tracker"""
    with get_http_client() as client:
        response = client.get(f"/report-tracker/{report_id}")
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Retrieved report tracker '{report_id}'"
        }


def _get_report_status_internal(report_id: str) -> dict:
    """Internal function to get report status"""
    with get_http_client() as client:
        response = client.get(f"/report-tracker/{report_id}/status")
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Retrieved status for report '{report_id}'"
        }


def _update_report_tracker_internal(report_id: str, action: str) -> dict:
    """Internal function to update report tracker"""
    with get_http_client() as client:
        response = client.put(
            f"/report-tracker/{report_id}",
            json={"action": action}
        )
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Report '{report_id}' updated with action '{action}'"
        }


def _assign_user_to_step_internal(
    report_id: str,
    stage_name: str,
    step_name: str,
    user_id: str,
    user_name: str,
    user_email: str,
    role: Optional[str] = None
) -> dict:
    """Internal function to assign user to step"""
    payload = {
        "report_id": report_id,
        "stage_name": stage_name,
        "step_name": step_name,
        "user_id": user_id,
        "user_name": user_name,
        "user_email": user_email
    }
    if role:
        payload["role"] = role
    
    with get_http_client() as client:
        response = client.post("/report-tracker/assign-user", json=payload)
        response.raise_for_status()
        data = response.json()
        return {
            "status": "success",
            "data": data,
            "message": f"Assigned {user_name} to {step_name} in {stage_name}"
        }


# ============================================================
# Tools - API Calls (with retry logic)
# ============================================================

@tool
def list_report_trackers() -> dict:
    """
    List all report tracker records.
    Returns a list of all reports with their IDs.
    Use this when the user wants to see all reports or find a report ID.
    """
    logger.info("[API] Listing all report trackers")
    
    if USE_MOCK_MODE:
        return {
            "status": "success",
            "data": [
                {"id": "uuid-1", "report_id": "RPT-001"},
                {"id": "uuid-2", "report_id": "RPT-002"}
            ],
            "message": "Listed 2 report trackers (mock)"
        }
    
    return api_call_with_retry(
        _list_report_trackers_internal,
        operation_name="list_report_trackers"
    )


@tool
def create_report_tracker(report_id: str, content_product_name: str) -> dict:
    """
    Create a new report tracker record.
    
    Args:
        report_id: Unique identifier for the report (e.g., "RPT-001", "PR-123")
        content_product_name: Name of the content product (e.g., "credit opinion", "Rating Report")
    
    Use this when the user wants to create/start a new report or workflow.
    """
    logger.info(f"[API] Creating report tracker: {report_id}, content_product: {content_product_name}")
    
    if USE_MOCK_MODE:
        return {
            "status": "success",
            "data": {
                "id": "uuid-new",
                "report_id": report_id,
                "workflow_json": {"workflow_name": "Publication Workflow"},
                "workflow_steps_json": {"progress_tracker": []},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "message": f"Created report tracker '{report_id}' (mock)"
        }
    
    return api_call_with_retry(
        _create_report_tracker_internal,
        report_id,
        content_product_name,
        operation_name=f"create_report_tracker({report_id})"
    )


@tool
def get_report_tracker(report_id: str) -> dict:
    """
    Get a report tracker by report_id.
    Returns full details including workflow_json and workflow_steps_json.
    
    Args:
        report_id: The report ID to look up
    
    Use this when the user wants to see details of a specific report.
    """
    logger.info(f"[API] Getting report tracker: {report_id}")
    
    if USE_MOCK_MODE:
        return {
            "status": "success",
            "data": {
                "id": "uuid-1",
                "report_id": report_id,
                "workflow_json": {"workflow_name": "Publication Workflow", "steps": []},
                "workflow_steps_json": {"progress_tracker": [
                    {"step_id": "initial_draft_001", "step_name": "Assemble Draft", "status": "completed"},
                    {"step_id": "initial_draft_002", "step_name": "Initial Draft", "status": "in_progress"}
                ]},
                "created_at": "2025-11-28T10:00:00Z",
                "updated_at": "2025-11-28T11:00:00Z"
            },
            "message": f"Retrieved report tracker '{report_id}' (mock)"
        }
    
    return api_call_with_retry(
        _get_report_tracker_internal,
        report_id,
        operation_name=f"get_report_tracker({report_id})"
    )


@tool
def get_report_status(report_id: str) -> dict:
    """
    Get the current status of a report.
    Returns progress_tracker with existing and future steps.
    
    Args:
        report_id: The report ID to check status for. The ID is typically in the format 'RPT-YYYYMMDDHHMMSS-XXXXXXXX' or 'PR-123'.
                   If the user asks for "report status", do NOT send "report" as the ID. 
                   Extract the actual ID from the context or ask the user if it's missing.
    
    Use this when the user wants to know the current status/progress of a report.
    """
    # Clean up report_id if it accidentally contains the word "report" or generic terms
    cleaned_id = report_id.strip()
    if cleaned_id.lower() in ["report", "this report", "the report"]:
        return {
            "status": "error",
            "message": "Invalid Report ID. Please provide the specific ID (e.g., RPT-20251027...)"
        }
    logger.info(f"[API] Getting report status: {report_id}")
    
    if USE_MOCK_MODE:
        return {
            "status": "success",
            "data": {
                "report_id": report_id,
                "progress_tracker": [
                    {"step_id": "initial_draft_001", "step_name": "Assemble Draft", "status": "completed"},
                    {"step_id": "initial_draft_002", "step_name": "Initial Draft", "status": "in_progress"},
                    {"step_id": "final_draft", "step_name": "Final Draft", "status": "pending"},
                    {"step_id": "copy_editing", "step_name": "Copy Editing", "status": "pending"}
                ]
            },
            "message": f"Retrieved status for report '{report_id}' (mock)"
        }
    
    return api_call_with_retry(
        _get_report_status_internal,
        report_id,
        operation_name=f"get_report_status({report_id})"
    )


@tool
def update_report_tracker(report_id: str, action: str) -> dict:
    """
    Update a report tracker with workflow action.
    
    Args:
        report_id: The report ID to update
        action: One of 7 supported actions:
            - Forward actions (move to success_goto): accept, submit, approve
            - Backward actions (move to fail_goto): reject, push_back, pull_back
    
    Forward actions (accept/submit/approve):
    - Mark current step as completed
    - Move to the next step
    
    Backward actions (reject/push_back/pull_back):
    - Mark current step as rejected
    - Move back to the previous step or create retry
    
    Use this when the user wants to approve/submit or reject/return a report step.
    """
    logger.info(f"[API] Updating report tracker: {report_id}, action: {action}")
    
    # Validate action
    action_lower = action.lower().strip()
    if action_lower not in WorkflowActionType.get_all_actions():
        valid_actions = ', '.join(sorted(WorkflowActionType.get_all_actions()))
        return {
            "status": "error",
            "message": f"Invalid action '{action}'. Must be one of: {valid_actions}"
        }
    
    if USE_MOCK_MODE:
        return {
            "status": "success",
            "data": {
                "id": "uuid-1",
                "report_id": report_id,
                "workflow_json": {"workflow_name": "Publication Workflow"},
                "workflow_steps_json": {"progress_tracker": [
                    {"step_id": "initial_draft_002", "step_name": "Initial Draft", "status": "completed" if WorkflowActionType.is_forward_action(action_lower) else "rejected"},
                    {"step_id": "final_draft" if WorkflowActionType.is_forward_action(action_lower) else "initial_draft_001", 
                     "step_name": "Final Draft" if WorkflowActionType.is_forward_action(action_lower) else "Assemble Draft", 
                     "status": "in_progress"}
                ]},
                "created_at": "2025-11-28T10:00:00Z",
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "message": f"Report '{report_id}' updated with action '{action_lower}' (mock)"
        }
    
    return api_call_with_retry(
        _update_report_tracker_internal,
        report_id,
        action_lower,
        operation_name=f"update_report_tracker({report_id}, {action_lower})"
    )


@tool
def assign_user_to_step(
    report_id: str,
    stage_name: str,
    step_name: str,
    user_id: str,
    user_name: str,
    user_email: str,
    role: Optional[str] = None
) -> dict:
    """
    Assign a user to a particular step in the workflow.
    
    Args:
        report_id: The report ID
        stage_name: Name of the stage (e.g., "Authoring", "Internal Review")
        step_name: Name of the step (e.g., "Initial Draft", "L1 Approval")
        user_id: User ID
        user_name: User's full name
        user_email: User's email
        role: Optional role of the user (e.g., "Senior Analyst", "Reviewer")
    
    Use this when the user wants to assign someone to a workflow step.
    """
    logger.info(f"[API] Assigning user to step: {report_id}, {stage_name}/{step_name}, user: {user_email}")
    
    if USE_MOCK_MODE:
        return {
            "status": "success",
            "data": {
                "id": "uuid-1",
                "report_id": report_id,
                "message": f"User '{user_name}' assigned to step '{step_name}'"
            },
            "message": f"Assigned {user_name} to {step_name} in {stage_name} (mock)"
        }
    
    return api_call_with_retry(
        _assign_user_to_step_internal,
        report_id,
        stage_name,
        step_name,
        user_id,
        user_name,
        user_email,
        role,
        operation_name=f"assign_user_to_step({report_id}, {step_name})"
    )


# All tools
tools = [
    list_report_trackers,
    create_report_tracker,
    get_report_tracker,
    get_report_status,
    update_report_tracker,
    assign_user_to_step
]


# ============================================================
# System Prompt
# ============================================================

system_prompt = """
You are a Workflow Management Agent that helps users manage document reports through their workflow lifecycle.

You have access to the following tools to interact with the Report Tracker API:

1. **list_report_trackers**: List all reports in the system
2. **create_report_tracker**: Create a new report (needs report_id and content_product_name)
3. **get_report_tracker**: Get full details of a specific report
4. **get_report_status**: Get the current status/progress of a report
5. **update_report_tracker**: Accept or reject the current step of a report
6. **assign_user_to_step**: Assign a user to a specific workflow step

Action Mapping:
- To APPROVE, ACCEPT, SUBMIT, COMPLETE a step → use update_report_tracker with action="accept"
- To REJECT, RETURN, SEND BACK a step → use update_report_tracker with action="reject"
- To CHECK STATUS, VIEW PROGRESS → use get_report_status
- To VIEW DETAILS, GET INFO → use get_report_tracker
- To CREATE, START NEW → use create_report_tracker
- To LIST ALL, SHOW ALL → use list_report_trackers
- To ASSIGN USER → use assign_user_to_step

Response Formatting:
- When listing reports, do not dump raw JSON. Present a clean summary table or list.
- When showing status, present it as a clear progress summary (e.g., "Current Step: X (In Progress)").
- Use Markdown for readability (bold, lists, etc.).
- Be concise but informative.

Ambiguity Handling:
- If the user's intent is unclear, try to infer the most likely action based on the context (e.g., "last one" likely refers to the most recently listed or discussed report).
- If inference is not possible, list the options or ask clarifying questions.
- When referring to "last report" or similar, FIRST use `list_report_trackers` to see available reports, THEN pick the most recent one (last in the list or highest ID) and perform the requested action on it. Do not just guess an ID or ask the user if you can look it up yourself.

Examples:
- "Accept report RPT-001" → update_report_tracker(report_id="RPT-001", action="accept")
- "Reject PR-123" → update_report_tracker(report_id="PR-123", action="reject")
- "What's the status of RPT-001?" → get_report_status(report_id="RPT-001")
- "Create a new credit opinion report" → create_report_tracker(report_id="<generate or ask>", content_product_name="credit opinion")
- "List all reports" → list_report_trackers()

Rules:
1. Always use the appropriate tool for the user's request
2. If report_id is not provided for an action that needs it, ask the user
3. For create operations, if report_id is not provided, suggest generating one or ask the user
4. Be helpful and confirm actions taken
5. If an error occurs, explain what went wrong

Be conversational and helpful while efficiently managing workflow operations.
"""


# ============================================================
# Agent Setup
# ============================================================

def is_placeholder(value):
    if not value:
        return True
    return any(kw in value.lower() for kw in ['your_', 'your-', 'placeholder', 'example', 'here'])


# Initialize LLM
llm = None
llm_with_tools = None

if USE_ANTHROPIC and not is_placeholder(ANTHROPIC_API_KEY):
    try:
        llm = ChatAnthropic(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.5
        )
        llm_with_tools = llm.bind_tools(tools)
        print("✅ Anthropic Claude initialized successfully")
    except Exception as e:
        print(f"⚠️ Failed to initialize Anthropic Claude: {e}")
        print("⚠️ Running in rule-based mode")

elif not is_placeholder(AZURE_OPENAI_API_KEY):
    try:
        llm = AzureChatOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            temperature=0
        )
        llm_with_tools = llm.bind_tools(tools)
        print("✅ Azure OpenAI initialized successfully")
    except Exception as e:
        print(f"⚠️ Failed to initialize Azure OpenAI: {e}")
        print("⚠️ Running in rule-based mode")
else:
    print("⚠️ No valid LLM configuration found, running in rule-based mode")


# ============================================================
# Agent Functions
# ============================================================

def run_agent_rule_based(user_input: str) -> dict:
    """Rule-based agent for when LLM is not available"""
    input_lower = user_input.lower().strip()
    
    # List reports
    if any(kw in input_lower for kw in ['list', 'show all', 'all reports']):
        return list_report_trackers.invoke({})
    
    # Get status
    if any(kw in input_lower for kw in ['status', 'progress']):
        # Try to extract report_id
        words = user_input.split()
        for word in words:
            if word.upper().startswith(('RPT', 'PR-', 'REPORT')):
                return get_report_status.invoke({"report_id": word})
        return {"status": "error", "message": "Please provide a report_id. Example: 'status of RPT-001'"}
    
    # Forward actions (submit, approve, accept)
    if any(kw in input_lower for kw in ['submit', 'approve', 'accept']):
        # Determine which action was used
        if 'submit' in input_lower:
            action = "submit"
        elif 'approve' in input_lower:
            action = "approve"
        else:
            action = "accept"
        
        words = user_input.split()
        for word in words:
            if word.upper().startswith(('RPT', 'PR-')):
                return update_report_tracker.invoke({"report_id": word, "action": action})
        return {"status": "error", "message": f"Please provide a report_id. Example: '{action} RPT-001'"}
    
    # Backward actions (push_back, pull_back, reject)
    if any(kw in input_lower for kw in ['push back', 'push_back', 'pull back', 'pull_back', 'reject', 'return', 'send back']):
        # Determine which action was used
        if 'push back' in input_lower or 'push_back' in input_lower:
            action = "push_back"
        elif 'pull back' in input_lower or 'pull_back' in input_lower:
            action = "pull_back"
        else:
            action = "reject"
        
        words = user_input.split()
        for word in words:
            if word.upper().startswith(('RPT', 'PR-')):
                return update_report_tracker.invoke({"report_id": word, "action": action})
        return {"status": "error", "message": f"Please provide a report_id. Example: '{action} RPT-001'"}
    
    # Get report details
    if any(kw in input_lower for kw in ['get', 'details', 'info']):
        words = user_input.split()
        for word in words:
            if word.upper().startswith(('RPT', 'PR-')):
                return get_report_tracker.invoke({"report_id": word})
        return {"status": "error", "message": "Please provide a report_id. Example: 'get RPT-001'"}
    
    return {
        "status": "info",
        "message": "I can help you with: list reports, check status, accept/reject reports, get report details. Please try again with a specific command."
    }


from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

# ... imports ...

# Global variable to maintain conversation history
history = []

def get_content_string(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join([str(item) for item in content])
    return str(content)

def run_agent(user_input: str) -> dict:
    """Main agent function with loop for multi-step reasoning and history"""
    global history
    
    if llm_with_tools is None:
        return run_agent_rule_based(user_input)
    
    # Manage history size to prevent context overflow
    if len(history) > 20:
        # Keep system prompt (index 0)
        # Find the earliest HumanMessage within the last 15 messages to preserve context window
        # while ensuring we don't cut in the middle of a tool execution chain
        trim_index = 0
        for i in range(len(history) - 10, len(history)):
             if i > 0 and isinstance(history[i], HumanMessage):
                 trim_index = i
                 break
        
        if trim_index > 0:
            history = [history[0]] + history[trim_index:]
        else:
            # Fallback: just take last 5 but ensure we don't start with ToolMessage
            trimmed = history[-5:]
            while trimmed and isinstance(trimmed[0], ToolMessage):
                trimmed.pop(0)
            history = [history[0]] + trimmed
    
    try:
        # Initialize history with system prompt if empty
        if not history:
            history = [SystemMessage(content=system_prompt)]
            
        # Add user input to history
        history.append(HumanMessage(content=user_input))
        
        # Agent Loop: Allow up to 10 turns of thought/action
        for _ in range(10):
            # Use the full history for context
            response = llm_with_tools.invoke(history)
            
            # Add the assistant's response to history
            history.append(response)
            
            if hasattr(response, 'tool_calls') and response.tool_calls:
                # Process all tool calls in this turn
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call['args']
                    tool_call_id = tool_call['id']
                    
                    logger.info(f"[AGENT] Calling tool: {tool_name} with args: {tool_args}")
                    
                    # Execute the appropriate tool
                    tool_map = {
                        'list_report_trackers': list_report_trackers,
                        'create_report_tracker': create_report_tracker,
                        'get_report_tracker': get_report_tracker,
                        'get_report_status': get_report_status,
                        'update_report_tracker': update_report_tracker,
                        'assign_user_to_step': assign_user_to_step
                    }
                    
                    if tool_name in tool_map:
                        try:
                            result = tool_map[tool_name].invoke(tool_args)
                            result_str = json.dumps(result, default=str)
                        except Exception as e:
                            result_str = json.dumps({"status": "error", "message": str(e)})
                    else:
                        result_str = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
                        
                    # Add tool output to history so LLM can see it
                    history.append(ToolMessage(content=result_str, tool_call_id=tool_call_id))
                
                # Loop continues to next iteration to let LLM process the tool output
                continue
            
            else:
                # No tool call - this is the final response to the user
                content = response.content if hasattr(response, 'content') else str(response)
                return {
                    "status": "info",
                    "message": get_content_string(content)
                }
                
        # If loop finishes without returning (max turns reached)
        content = response.content if hasattr(response, 'content') else ""
        return {
             "status": "info",
             "message": "I completed the actions but reached my limit. " + get_content_string(content)
        }
    
    except Exception as e:
        logger.error(f"Agent error: {e}")
        # Fall back to rule-based
        return run_agent_rule_based(user_input)


# ============================================================
# Interactive CLI
# ============================================================

def main():
    """Interactive command-line interface"""
    print("\n" + "="*60)
    print("Workflow Management Agent")
    print("="*60)
    print("\nCommands you can try:")
    print("  - 'list reports' or 'show all'")
    print("  - 'status of RPT-001'")
    print("  - 'accept RPT-001'")
    print("  - 'reject RPT-001'")
    print("  - 'get details for RPT-001'")
    print("  - 'create report for credit opinion'")
    print("  - 'quit' or 'exit' to stop")
    print("\n" + "-"*60)
    
    if USE_MOCK_MODE:
        print("⚠️  Running in MOCK MODE (no actual API calls)")
    else:
        print(f"📡 API Base URL: {API_BASE_URL}")
    
    print(f"📝 Log file: {LOG_FILENAME}")
    print(f"🔄 Max retries: {MAX_RETRIES}")
    print("-"*60 + "\n")
    
    logger.info("Interactive session started")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                logger.info("Session ended by user")
                print(f"\nGoodbye! Log saved to: {LOG_FILENAME}")
                break
            
            # Log user input
            logger.info(f"User input: {user_input}")
            
            result = run_agent(user_input)
            
            # Log agent response
            logger.info(f"Agent response: {json.dumps(result, default=str)}")
            
            print(f"\nAgent: {json.dumps(result, indent=2, default=str)}\n")
            
        except KeyboardInterrupt:
            logger.info("Session interrupted by user")
            print(f"\nGoodbye! Log saved to: {LOG_FILENAME}")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            print(f"\nError: {e}\n")


# ============================================================
# Test Scenarios
# ============================================================

def run_tests():
    """Run test scenarios"""
    print("\n" + "="*60)
    print("API AGENT TEST SCENARIOS")
    print("="*60)
    
    test_cases = [
        ("List all reports", "list all reports"),
        ("Get status", "what's the status of RPT-001?"),
        ("Accept report", "accept RPT-001"),
        ("Reject report", "reject PR-123"),
        ("Get details", "show me details of RPT-001"),
        ("Create report", "create a new report RPT-NEW for credit opinion"),
    ]
    
    for name, user_input in test_cases:
        print(f"\n--- Test: {name} ---")
        print(f"Input: {user_input}")
        result = run_agent(user_input)
        print(f"Result: {json.dumps(result, indent=2, default=str)}")
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_tests()
    else:
        main()

