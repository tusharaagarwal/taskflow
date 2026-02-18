# Deprecated SQS consumer implementations (reference only)

These modules are **deprecated** and kept for reference only.

| File | Original location | Description |
|------|-------------------|-------------|
| `sqs_consumer_deprecated.py` | `server/sqs_consumer.py` | SQSMessageConsumer – used by agent_service for agent SQS consumption |
| `aws_consumer_deprecated.py` | `app/services/aws/consumer.py` | MessageConsumer – was used by assembler completion listener (separate process) |

**New implementation:** Assembler completion SQS consumption now runs **in-process** in the Workflow Orchestrator API. See:

- `app/services/sqs_consumer.py` – new async consumer (AssemblerCompletionSQSConsumer), started in FastAPI lifespan from `app/main.py`.

To run the assembler completion consumer, start the API (e.g. `uvicorn app.main:app` or `poetry run python scripts/run_assembler_completion_consumer.py`).
