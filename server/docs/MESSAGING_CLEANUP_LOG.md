# Messaging Cleanup – Changelog

**Branch:** `cleanup-messaging-consolidation`  
**Scope:** All changes are inside the `workflow_orchestrator` project.

This document records every change made during the messaging/SQS cleanup so we retain the desired consumers and publishers and remove only the legacy code.

---

## What we are keeping (current implementation)

- **Assembler completion consumer:** `app/services/sqs_consumer.py` – in-process SQS consumer (AssemblerCompletionSQSConsumer), started in FastAPI lifespan (`app/main.py`). All logic (payload extraction, handler, notify) in one file; no imports from `app.services.aws.listeners` or `app.services.aws.consumer`.
- **Publisher:** `MessagePublisher` (`app/services/aws/publisher.py`)
- **MessagingService** (`app/services/aws/messaging_service.py`) – `notify_assembler_to_start`, `notify_consumers`; `start_assembler_completion_listener` / `stop_assembler_completion_listener` are no-ops (consumer runs in app.services.sqs_consumer).
- **Agent service** (`server/agent_service.py`) still uses `server/sqs_consumer.py` (deprecated) for agent SQS consumption; see `server/deprecated/` for reference copies.
- **Deprecated (reference only):** `MessageConsumer` and `SQSMessageConsumer` copies in `server/deprecated/`; `app/services/aws/listeners.py` kept for reference (logic reimplemented in app.services.sqs_consumer).

---

## What we are removing

- `app/services/aws_messaging_service.py` (entire file – `AWSMessagingService`, `SQSConsumer`, etc.)
- `app/services/messaging_manager.py` (entire file)
- `server/docs/CONSUMER_CONSOLIDATION.md` (optional doc)
- References to `worker_sqs.py` in docs and router (optional)

---

## Messaging APIs (`app/routers/v1/messaging.py`)

These endpoints are **manual handles**: they let you check messaging status and notify consumers on demand, in addition to the automatic notifications that happen from other code (e.g. report creation, assembler completion listener).

Both APIs respect `settings.messaging_enabled`. The status and config they use/report are the same as the aws/* publisher and consumer (same topic/queue names from settings).

### 1. GET `/v1/messaging/status`

**Purpose:** Check whether messaging is enabled and see the publish-side config (region, topic/queue names). The in-process SQS consumer is started in app lifespan, not by this endpoint.

| Aspect | Details |
|--------|---------|
| **Method** | `GET` |
| **Path** | `/v1/messaging/status` |
| **Query/Body** | None |

**Response when messaging is disabled (200):**
```json
{
  "status": "disabled",
  "message": "Messaging services are disabled in configuration",
  "sqs_consumer_note": "Assembler completion SQS consumer runs in-process when messaging is enabled"
}
```

**Response when messaging is enabled (200):**
```json
{
  "status": "healthy",
  "sqs_consumer": "in_process",
  "aws_connectivity": "connected",
  "config": {
    "region": "ap-south-1",
    "assembler_task_topic": "<from settings>",
    "assembler_completion_queue": "<from settings>",
    "consumer_notification_topic": "<from settings>"
  },
  "sqs_consumer_note": "Assembler completion SQS consumer runs in-process (app.services.sqs_consumer)."
}
```

**Errors:** 500 if an exception occurs while building the response.

---

### 2. POST `/v1/messaging/publish-report-update`

**Purpose:** Manually publish a report update to consumers. Calls `get_messaging_service().notify_consumers(...)` so subscribers to the consumer-notification SNS topic (and optionally SQS) receive the update.

| Aspect | Details |
|--------|---------|
| **Method** | `POST` |
| **Path** | `/v1/messaging/publish-report-update` |
| **Body (JSON)** | `report_id` (string, required), `update_type` (string, required), `data` (object, required), `subject` (string, optional) |

**Example request:**
```json
{
  "report_id": "RPT-20250115120000-abc123",
  "update_type": "draft_completed",
  "data": {
    "status": "first_draft_completed",
    "draft_url": "https://...",
    "step": "initial_draft_001"
  }
}
```

**Response on success (200):**
```json
{
  "message": "Report update published successfully",
  "report_id": "RPT-20250115120000-abc123",
  "update_type": "draft_completed"
}
```

**Errors:**
- 503 if `messaging_enabled` is false (detail: "Messaging services are disabled").
- 500 if publish fails or another exception occurs (detail: "Failed to publish report update").

**Note:** Consumers can also be notified by other code paths (e.g. assembler completion listener, workflow_message_handlers). This API is the manual way to trigger a consumer notification.

---

## AWS configuration (for refactoring)

The project has **two separate AWS config sources**. Use this when refactoring so you don’t assume a single source.

### 1. Orchestrator aws/* path (API, report creation, assembler completion, notify consumers)

**Where it’s maintained**

- **`server/config_loader.py`** – `ConfigManager.get_aws_messaging_config()` (lines ~187–208) returns the full dict.
- **`server/config_{environment}.json`** – e.g. `config_dev.json`; holds values per environment (keys: `aws_region`, `messaging_enabled`, `assembler_task_queue_name`, etc.).
- **`server/.env_{environment}`** – e.g. `.env_dev`; maps **env var name → config key** (e.g. `AWS_REGION=aws_region`). Actual env vars override the JSON when set.
- **`server/app/config/config.py`** – On load, calls `config_manager.get_aws_messaging_config()` and assigns every key onto **`settings`**. All aws/* code and messaging APIs use **`settings`** only.

**Precedence:** Environment variable (if set) → value from `config_{env}.json` for the mapped key → default in `get_aws_messaging_config()`.

**Full set of keys (this is the whole config for this path)**

| Config | Env var (override) | JSON key (e.g. config_dev.json) | Purpose |
|--------|--------------------|----------------------------------|---------|
| Region | `AWS_REGION` | `aws_region` | AWS region (e.g. ap-south-1) |
| Credentials | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | `aws_access_key_id`, etc. | Optional; empty → boto default chain |
| Messaging on/off | `MESSAGING_ENABLED` | `messaging_enabled` | Gate for publish + assembler completion listener |
| Assembler task queue | `ASSEMBLER_TASK_QUEUE_NAME` | `assembler_task_queue_name` | Queue for notify_assembler_to_start |
| Assembler task topic | `ASSEMBLER_TASK_TOPIC_NAME` | `assembler_task_topic_name` | SNS topic for assembler task |
| Assembler message group | `ASSEMBLER_MESSAGE_GROUP_ID` | `assembler_message_group_id` | FIFO group for assembler |
| Assembler completion queue | `ASSEMBLER_COMPLETION_QUEUE_NAME` | `assembler_completion_queue_name` | Queue **assembler-to-orchestrator**: orchestrator consumes from it when assembler notifies completion. |
| Consumer notification topic | `CONSUMER_NOTIFICATION_TOPIC_NAME` | `consumer_notification_topic_name` | SNS for notify_consumers |
| Consumer notification queue | `CONSUMER_NOTIFICATION_QUEUE_NAME` | `consumer_notification_queue_name` | Optional SQS for notify_consumers |
| Consumer message group | `CONSUMER_NOTIFICATION_MESSAGE_GROUP_ID` | `consumer_notification_message_group_id` | FIFO group for consumer topic |
| SQS behaviour | `SQS_MAX_MESSAGES`, `SQS_WAIT_TIME_SECONDS`, `SQS_VISIBILITY_TIMEOUT`, `SQS_POLL_INTERVAL`, `SQS_AUTO_DELETE_MESSAGES` | Same (snake_case in JSON) | Consumer long-poll and delete behaviour |
| SNS default group | `SNS_DEFAULT_MESSAGE_GROUP_ID` | `sns_default_message_group_id` | Default FIFO group for SNS |
| Orchestrator API base URL | `ORCHESTRATOR_API_BASE_URL` | `orchestrator_api_base_url` | Base URL for report-tracker PUT from assembler completion handler (consumer process). |

**Used by:** `app/services/sqs_consumer.py`, `app/services/aws/publisher.py`, `app/services/aws/messaging_service.py`, report_tracker router (notify_assembler_to_start), messaging router, workflow_message_handlers.

**Required AWS resources (must exist in your account/region)**

| Resource | Config key / default name | Notes |
|----------|---------------------------|--------|
| **SNS topic** | `consumer_notification_topic_name` → default **orchestrator-to-authoring** | Used when notifying consumer applications (e.g. after assembler completion). Must **not** be the same as the assembler completion queue/topic (e.g. assembler-to-orchestrator) or messages will loop back. Create in AWS SNS in the same region. |
| **SNS topic** | `assembler_task_topic_name` → default **orchestrator-to-assembler** | Used when sending assembly tasks to the assembler. Must exist in the same region. |
| **SQS queue** | `assembler_completion_queue_name` → default `assembler-to-orchestrator` | Orchestrator consumes assembler completion messages from this queue. Create in AWS SQS if missing. |
| **SQS queue** | `assembler_task_queue_name` → default `orchestrator-to-assembler` | Used for assembler tasks. Create in AWS SQS if missing. |
| **SQS queue** | `consumer_notification_queue_name` → default **orchestrator-to-authoring** | Queue for consumer applications (e.g. authoring) to receive orchestrator notifications. Subscribe to the consumer notification SNS topic or receive directly; must not be assembler-to-orchestrator. |

---

### 2. Agent path (agent_service + sqs_consumer)

**Where it’s maintained**

- **`server/aws_config.json`** only. No ConfigManager, no `config_loader`, no `settings` for this path.
- **`server/sqs_consumer.py`** – `load_aws_config()` reads this file. **`agent_service.py`** uses it indirectly via `create_consumer_from_config()`.

**What’s in the file**

| Config | Key in aws_config.json | Purpose |
|--------|------------------------|---------|
| Region | `region` | AWS region |
| Queue name | `resources.sqs_queue` | Queue the agent consumes from |
| Credentials | `credentials.access_key_id`, `secret_access_key`, `session_token` | Optional; often empty → boto default / env |

**Used by:** `server/sqs_consumer.py`, `server/agent_service.py` (for the agent SQS consumer only). **Not** used by aws/* or the messaging APIs.

---

### Summary for refactoring

- **Orchestrator aws/* messaging** → single source: **config_loader.get_aws_messaging_config()** → **settings**. The dict in `config_loader.py` (lines ~190–207) is the **complete** set for this path.
- **Agent SQS consumer** → single source: **server/aws_config.json**; agent path does not use config_loader or settings for AWS.
- Any refactor that unifies or moves AWS config must account for both sources and both consumers (MessageConsumer vs SQSMessageConsumer).

---

### Assembler → Orchestrator notification queue

When the **assembler** wants to notify the **orchestrator** (e.g. draft completed), it sends to the SQS queue **`assembler-to-orchestrator`**. The orchestrator consumes from this queue via the in-process consumer (`app/services/sqs_consumer.py`), started in FastAPI lifespan.

- **Config key:** `assembler_completion_queue_name` (env: `ASSEMBLER_COMPLETION_QUEUE_NAME`).
- **Default value:** `assembler-to-orchestrator` (set in `config_loader.py`, `config_dev.json`, and `app/config/config.py` fallback).
- **Assembler side:** Must send completion messages to the queue named `assembler-to-orchestrator` (create the queue in AWS SQS and grant orchestrator consume permissions).

---

## Assembler completion message format

The **assembler** sends JSON messages to the queue **assembler-to-orchestrator**. The orchestrator’s consumer runs **in-process** (app.services.sqs_consumer, started in app.main lifespan). On receipt of a completion message, the handler in that module calls the report-tracker API (HTTP PUT) and notifies consumers (SNS).

### Payload schema (assembler → queue)

Only the following payload is used. Old fields (workflow_id, draft_url, app_data, error_message, message_id, timestamp, type) are no longer used.

| Field | Required | Description |
|-------|----------|-------------|
| `report_id` | Yes | Report identifier. |
| `status` | Yes | `"completed"` or `"failed"`. |
| `pr_id` | No | PR identifier. |
| `transaction_id` | No | Transaction identifier. |
| `content_type` | No | Content type. |
| `step_name` | No | Step name (e.g. `"assembled_draft"`). |
| `completed_date` | No | Completion date (e.g. ISO8601). |

### Flow

1. **Consumer** (separate process) receives a message from **assembler-to-orchestrator**.
2. **Handler** parses payload; validates `report_id` and `status`.
3. If `status == "completed"`:
   - Handler sends **PUT** `{ORCHESTRATOR_API_BASE_URL}/v1/report-tracker/{report_id}` with body `{"action": "accept"}` only (no app_data, no workflow_id/draft_url).
   - Orchestrator API updates the report tracker (accept on current step).
   - On 2xx success, handler calls `get_messaging_service().notify_consumers(report_id, event_type="draft_completed", pr_id=..., transaction_id=..., status="completed")`. Consumer notifications use report_id, pr_id, and transaction_id (no workflow_id or draft_url).
4. On failure (missing report_id, API error, non-2xx), handler returns `False` so the message can be retried; on success returns `True` and the consumer deletes the message.

### Config for the consumer process

The consumer process must know the orchestrator API base URL so it can perform the report-tracker update via HTTP.

| Config | Env var (override) | JSON key | Purpose |
|--------|--------------------|----------|---------|
| Orchestrator API base URL | `ORCHESTRATOR_API_BASE_URL` | `orchestrator_api_base_url` | Base URL of the orchestrator API (default derived from host/port, e.g. `http://127.0.0.1:8003`). Used by the assembler completion handler for `PUT .../v1/report-tracker/{report_id}`. |

Set this in `config_{environment}.json` and/or `.env_{environment}` (env var maps to the JSON key). Default base URL is derived from server host/port (e.g. `http://127.0.0.1:8003`). The API process must be running and reachable when the consumer processes messages.

---

## Standalone scripts (testing)

| Script | Purpose |
|--------|---------|
| **`scripts/run_assembler_completion_consumer.py`** | **Starts the API** (uvicorn). The in-process SQS consumer (app.services.sqs_consumer) consumes from **assembler-to-orchestrator** and runs the handler (PUT report-tracker, then notify consumers). |
| **`scripts/run_consumer_notification_consumer.py`** | Consumes from **orchestrator-to-authoring** queue (consumer notification queue); logs each message for testing. Run in a separate terminal to verify notifications reach consumer apps. |
| **`scripts/publish_dummy_assembler_completion.py`** | Publishes a dummy assembler completion message to **assembler-to-orchestrator** SQS for testing without the real content-assembler. |

See **TESTING_ASSEMBLER_FLOW.md** for full steps (AWS SSO, refresh credentials, start backends, run both consumers, publish dummy message).

---

## Changelog

| Date       | Change |
|-----------|--------|
| *(initial)* | Branch `cleanup-messaging-consolidation` created. This log file added. |
| *(cleanup)* | **Refactored** `app/routers/v1/messaging.py`: removed dependency on `messaging_manager`; now uses `get_messaging_service()` from `app.services.aws.messaging_service` for publish; status endpoint returns health/config without calling removed code; removed `worker_sqs.py` from response text. |
| *(cleanup)* | **Refactored** `app/services/workflow_message_handlers.py`: removed `aws_messaging_service` and `MessageType`; all `publish_report_update` calls replaced with `get_messaging_service().notify_consumers(...)`; `register_message_handlers()` is now a no-op (assembler completion handled by `app.services.sqs_consumer`). |
| *(cleanup)* | **Deleted** `app/services/aws_messaging_service.py` (AWSMessagingService, SQSConsumer, SNSPublisher). |
| *(cleanup)* | **Deleted** `app/services/messaging_manager.py` (MessagingManager). |
| *(cleanup)* | **Deleted** `server/docs/CONSUMER_CONSOLIDATION.md`. |
| *(cleanup)* | **Tests:** No test files referenced the removed modules; no tests removed. |
| *(doc)* | **Documented** Messaging APIs in this file: `GET /v1/messaging/status` and `POST /v1/messaging/publish-report-update` (purpose, request/response, errors). |
| *(doc)* | **Documented** AWS configuration: two sources (config_loader → settings for aws/* path; aws_config.json for agent path), full key list, precedence, and refactoring notes. |
| *(config)* | **Assembler → orchestrator queue:** Set `assembler_completion_queue_name` to **assembler-to-orchestrator** so when the assembler notifies the orchestrator, it sends to this queue and the orchestrator consumes from it. Updated `config_loader.py` default, `config_dev.json`, and `app/config/config.py` fallback. |
| *(feature)* | **Assembler completion flow:** On receipt of assembler completion message with `status == "completed"`, handler now (1) PUTs to orchestrator API `PUT /v1/report-tracker/{report_id}` with `action=accept` and optional `app_data`, (2) on success calls `notify_draft_completed`. Added `ORCHESTRATOR_API_BASE_URL` / `orchestrator_api_base_url` for the consumer process. Documented payload schema and flow in "Assembler completion message format" and config table. |
| *(config)* | **Topic/queue alignment:** `assembler_task_topic_name` default → **orchestrator-to-assembler**; `consumer_notification_topic_name` and `consumer_notification_queue_name` default → **orchestrator-to-authoring** (separate from assembler-to-orchestrator to avoid feedback loop). Updated config_loader, config_dev.json, app config. |
| *(scripts)* | **Standalone scripts:** Added `scripts/run_assembler_completion_consumer.py`, `scripts/run_consumer_notification_consumer.py`, `scripts/publish_dummy_assembler_completion.py`. See "Standalone scripts (testing)" and TESTING_ASSEMBLER_FLOW.md. |
| *(doc)* | **TESTING_ASSEMBLER_FLOW.md:** Full testing guide (AWS SSO, refresh credentials, start backends, content-assembler subscribe, assembler completion consumer, dummy publish, consumer notification consumer as Step 6). Use Set-Location for PowerShell. |
| *(payload)* | **Assembler completion:** Dropped old payload. New payload only: report_id, pr_id, transaction_id, content_type, step_name, status, completed_date. PUT body is `{"action": "accept"}` only. workflow_id and draft_url are not forwarded to consumer applications (notify_draft_completed called with None). Updated listeners, messaging_service docstring, publish_dummy_assembler_completion.py, MESSAGING_CLEANUP_LOG.md, TESTING_ASSEMBLER_FLOW.md. |

---

*Add new rows above this line as you make changes.*
