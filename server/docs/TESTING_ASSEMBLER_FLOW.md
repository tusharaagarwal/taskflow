# Testing the assembler completion flow

This guide describes how to run the full stack to test messages from the content assembler to the workflow orchestrator (assembler-to-orchestrator queue) and the orchestrator’s report-tracker update + consumer notification.

## Prerequisites

- AWS CLI with SSO configured (profile e.g. `AWSPowerUserAccess-062700375195`)
- Poetry installed for each app
- Workflow orchestrator API will run on **port 8003** by default

## Step 1: AWS SSO login

In a terminal:

```powershell
aws sso login --profile AWSPowerUserAccess-062700375195
```

## Step 2: Refresh AWS credentials

From the **cognida** repo root (so `scripts/` is available):

```powershell
Set-Location "c:\Users\Tusshar Agarwaal\projects\cognida"
.\scripts\refresh_aws_credentials.ps1 -Profile AWSPowerUserAccess-062700375195
```

This writes credentials so all Cognida apps and terminals can use them.

## Step 3: Start all backends

From **workflow_orchestrator** (or cognida root, adjust path as needed):

```powershell
Set-Location "c:\Users\Tusshar Agarwaal\projects\cognida\workflow_orchestrator"
.\scripts\start-all-cognida-backends.ps1
```

This opens separate windows for:

- workflow_orchestrator (port **8003**)
- content-authoring (8004)
- content-assembler (8005)
- content-designer (8006)
- platform-services (8007)
- dummy-upstream (8008)
- workspace (8009)
- notifications (8010)

Keep these running. The orchestrator API runs the assembler completion SQS consumer in-process (app.services.sqs_consumer), so no separate consumer process is required.

## Step 4: Content assembler – subscribe to messages

In a **new terminal** (content-assembler subscribes to its queue and can publish to assembler-to-orchestrator):

```powershell
Set-Location "c:\Users\Tusshar Agarwaal\projects\cognida\content-assembler\server"
poetry run python app/utils/aws/subscribe_messages.py
```

Adjust path if your repo layout differs (e.g. `content_assembler`). Leave this running.

## Step 5: Workflow orchestrator – API (assembler completion consumer in-process)

The assembler completion consumer runs **inside** the Workflow Orchestrator API process (started in FastAPI lifespan). So either:

- **Option A:** The orchestrator is already running from Step 3 (`start-all-cognida-backends.ps1`). The in-process consumer is active as soon as the API is up; no separate step needed.

- **Option B:** To run only the orchestrator (e.g. in a separate terminal):

```powershell
Set-Location "c:\Users\Tusshar Agarwaal\projects\cognida\workflow_orchestrator\server"
poetry run python scripts/run_assembler_completion_consumer.py
```

This script **starts the API** (uvicorn); the SQS consumer runs in-process and consumes from **assembler-to-orchestrator**. Stop with **Ctrl+C**.

## Publishing a dummy message (no content-assembler)

To test the orchestrator consumer without running the real content-assembler, publish a dummy message to the **assembler-to-orchestrator** queue:

```powershell
Set-Location "c:\Users\Tusshar Agarwaal\projects\cognida\workflow_orchestrator\server"
poetry run python scripts/publish_dummy_assembler_completion.py
```

Payload format sent by the script: `report_id`, `pr_id`, `transaction_id`, `content_type`, `step_name`, `status`, `completed_date` (old fields such as workflow_id and draft_url are no longer used; they are not forwarded to consumer applications).

Optional arguments:

- `--report-id RPT-XXX` – Use an existing report ID from your DB so the PUT report-tracker call succeeds (default: `RPT-DUMMY-001`, may 404 if the report does not exist).
- `--status completed` or `--status failed` – Message status (default: `completed`).
- `--pr-id`, `--transaction-id`, `--content-type`, `--step-name`, `--completed-date` – Optional payload fields (defaults: PR-DUMMY-001, TXN-DUMMY-001, empty, assembled_draft, now UTC).
- `--queue NAME` – Override queue name (default: from config).

Example with a real report ID:

```powershell
poetry run python scripts/publish_dummy_assembler_completion.py --report-id RPT-20250115120000-ABC123
```

Ensure the **orchestrator API** is up (Step 3 or Step 5); the in-process SQS consumer will process the message and apply the report-tracker update.

## Step 6: Consumer notification queue (orchestrator-to-workspace)

To test that notifications from the orchestrator (e.g. draft_completed) reach the **consumer applications** queue, run a consumer that reads from **orchestrator-to-workspace**:

```powershell
Set-Location "c:\Users\Tusshar Agarwaal\projects\cognida\workflow_orchestrator\server"
poetry run python scripts/run_consumer_notification_consumer.py
```

This script consumes from `consumer_notification_queue_name` (default **orchestrator-to-workspace**), logs each message (report_id, pr_id, transaction_id, type, status), and deletes it after processing. Consumer notifications use `notify_consumers()` with report_id, pr_id, transaction_id, and event_type (e.g. draft_completed). Use it to verify that when the assembler completion handler runs, the notification reaches this queue. Stop with **Ctrl+C**.

## Summary of terminals

| Terminal | Purpose |
|----------|--------|
| 1 | `aws sso login` then `refresh_aws_credentials.ps1` (can reuse for step 3) |
| 2 | `start-all-cognida-backends.ps1` (opens multiple app windows; orchestrator runs SQS consumer in-process) |
| 3 | content-assembler: `poetry run python app/utils/aws/subscribe_messages.py` |
| 4 | (Optional) workflow_orchestrator: `poetry run python scripts/run_assembler_completion_consumer.py` – starts API only if not using start-all-cognida-backends |
| 5 | workflow_orchestrator: `poetry run python scripts/run_consumer_notification_consumer.py` (test orchestrator-to-workspace queue) |

## Troubleshooting: "Topic does not exist" (SNS)

If you see:

```text
Failed to publish to SNS topic 'workflow_orchestrator_consumer_notifications.fifo': Topic does not exist
```

the **consumer notification SNS topic** is not present in your AWS account/region. Either:

1. **Create the topic in AWS** (same region as in config, e.g. `ap-south-1`):
   - In AWS Console: SNS → Create topic → Type: **FIFO**, Name: `workflow_orchestrator_consumer_notifications.fifo`.
   - Or CLI: `aws sns create-topic --name workflow_orchestrator_consumer_notifications.fifo --attributes FifoTopic=true --region ap-south-1`

2. **Or use an existing topic name** by overriding config:
   - Set env var: `$env:CONSUMER_NOTIFICATION_TOPIC_NAME = "your-existing-fifo-topic.fifo"`
   - Or in `config_dev.json`: `"consumer_notification_topic_name": "your-existing-fifo-topic.fifo"` (default is **orchestrator-to-workspace**)

The topic **must be FIFO** (name must end with `.fifo`). Same applies to `assembler_task_topic_name` (`workflow_orchestrator_topic.fifo`) if you use assembler notifications.

## Config notes

- **workflow_orchestrator** runs on **8003** (see `app/config/config.py` default `PORT`, `config_dev.json`, and `start-all-cognida-backends.ps1`).
- **ORCHESTRATOR_API_BASE_URL** (or `orchestrator_api_base_url` in config) must point at the running API (e.g. `http://localhost:8003`). The consumer script reads this and uses it for the report-tracker PUT.
- Queue name for assembler completion is **assembler-to-orchestrator** (`assembler_completion_queue_name` in config).

## See also

- [MESSAGING_CLEANUP_LOG.md](MESSAGING_CLEANUP_LOG.md) – assembler completion message format and flow
- Plan: assembler completion flow (format, report-tracker update, consumer notify)
