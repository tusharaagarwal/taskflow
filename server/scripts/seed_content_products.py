#!/usr/bin/env python3
"""Seed content products with guarded, idempotent operations."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))

from app.db.database import AsyncSessionLocal
from app.models.content_product import ContentProduct
from app.models.workflow import Workflow
from app.seed_data.content_product_seed_data import CONTENT_PRODUCT_SEED_ROWS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed content_product table data safely.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Insert/update content product seed rows.")
    seed_parser.add_argument("--dry-run", action="store_true", help="Preview changes without mutating data.")

    list_parser = subparsers.add_parser("list", help="List seeded content products.")
    list_parser.add_argument("--all", action="store_true", help="List all rows in content_product table.")

    clear_parser = subparsers.add_parser("clear", help="Delete content product seed rows.")
    clear_parser.add_argument("--force", action="store_true", help="Required to allow deletion.")
    clear_parser.add_argument("--dry-run", action="store_true", help="Preview deletions without mutating data.")

    return parser


def _row_to_dict(row: ContentProduct) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "workflow_id": row.workflow_id,
    }


async def _validate_referenced_workflows(session) -> None:
    workflow_ids = sorted({row["workflow_id"] for row in CONTENT_PRODUCT_SEED_ROWS})
    existing_ids = set((await session.execute(select(Workflow.workflow_id))).scalars().all())
    missing = [workflow_id for workflow_id in workflow_ids if workflow_id not in existing_ids]
    if missing:
        missing_str = ", ".join(str(item) for item in missing)
        raise ValueError(
            "Missing referenced workflow rows. Seed workflows first. "
            f"Missing workflow_id values: {missing_str}"
        )


async def _compute_seed_plan(session) -> tuple[dict[int, ContentProduct], list[dict[str, Any]]]:
    target_ids = [row["id"] for row in CONTENT_PRODUCT_SEED_ROWS]
    existing_rows = (
        await session.execute(select(ContentProduct).where(ContentProduct.id.in_(target_ids)))
    ).scalars().all()
    existing_by_id = {row.id: row for row in existing_rows}

    plan: list[dict[str, Any]] = []
    for row in CONTENT_PRODUCT_SEED_ROWS:
        existing = existing_by_id.get(row["id"])
        if existing is None:
            plan.append({"action": "insert", "row": row})
            continue

        if existing.name != row["name"] or existing.workflow_id != row["workflow_id"]:
            plan.append({"action": "update", "row": row})
        else:
            plan.append({"action": "skip", "row": row})

    return existing_by_id, plan


async def _sync_sequence_if_postgres(session) -> None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return

    await session.execute(
        text(
            """
            SELECT setval(
                'content_product_id_seq',
                GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.content_product), 1),
                true
            )
            WHERE EXISTS (
                SELECT 1
                FROM pg_class
                WHERE relname = 'content_product_id_seq'
            );
            """
        )
    )


async def seed_content_products(session, *, dry_run: bool = False) -> dict[str, Any]:
    await _validate_referenced_workflows(session)
    existing_by_id, plan = await _compute_seed_plan(session)

    inserted = sum(1 for item in plan if item["action"] == "insert")
    updated = sum(1 for item in plan if item["action"] == "update")
    skipped = sum(1 for item in plan if item["action"] == "skip")

    if not dry_run:
        try:
            for item in plan:
                row = item["row"]
                action = item["action"]
                if action == "insert":
                    session.add(
                        ContentProduct(
                            id=row["id"],
                            name=row["name"],
                            workflow_id=row["workflow_id"],
                        )
                    )
                elif action == "update":
                    existing = existing_by_id[row["id"]]
                    existing.name = row["name"]
                    existing.workflow_id = row["workflow_id"]

            await _sync_sequence_if_postgres(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "command": "seed",
        "dry_run": dry_run,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "planned_actions": [
            {"action": item["action"], "id": item["row"]["id"], "name": item["row"]["name"]}
            for item in plan
        ],
    }


async def list_content_products(session, *, list_all: bool = False) -> dict[str, Any]:
    stmt = select(ContentProduct)
    if not list_all:
        target_ids = [row["id"] for row in CONTENT_PRODUCT_SEED_ROWS]
        stmt = stmt.where(ContentProduct.id.in_(target_ids))
    rows = (await session.execute(stmt.order_by(ContentProduct.id.asc()))).scalars().all()
    return {
        "command": "list",
        "count": len(rows),
        "rows": [_row_to_dict(row) for row in rows],
    }


async def clear_content_products(session, *, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    target_ids = [row["id"] for row in CONTENT_PRODUCT_SEED_ROWS]
    existing_rows = (
        await session.execute(select(ContentProduct).where(ContentProduct.id.in_(target_ids)))
    ).scalars().all()
    existing_ids = sorted(row.id for row in existing_rows)

    if not force:
        return {
            "command": "clear",
            "dry_run": dry_run,
            "deleted": 0,
            "force_required": True,
            "message": "No-op. Re-run with --force to delete seed rows.",
            "target_ids_found": existing_ids,
        }

    if dry_run:
        return {
            "command": "clear",
            "dry_run": True,
            "deleted": len(existing_ids),
            "target_ids_found": existing_ids,
        }

    try:
        for row in existing_rows:
            await session.delete(row)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {
        "command": "clear",
        "dry_run": False,
        "deleted": len(existing_ids),
        "target_ids_found": existing_ids,
    }


async def _run_command(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        if args.command == "seed":
            result = await seed_content_products(session, dry_run=args.dry_run)
        elif args.command == "list":
            result = await list_content_products(session, list_all=args.all)
        elif args.command == "clear":
            result = await clear_content_products(session, force=args.force, dry_run=args.dry_run)
        else:
            raise ValueError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_run_command(args))


if __name__ == "__main__":
    raise SystemExit(main())

