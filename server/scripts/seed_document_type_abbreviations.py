#!/usr/bin/env python3
"""Seed document type abbreviations with guarded, idempotent operations."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))

from app.db.database import AsyncSessionLocal
from app.models.abbreviation import DocumentTypeAbbreviation
from app.seed_data.abbreviation_seed_data import ABBREVIATION_SEED_ROWS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed document type abbreviations safely.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Insert/update abbreviation seed rows.")
    seed_parser.add_argument("--dry-run", action="store_true", help="Preview changes without mutating data.")

    list_parser = subparsers.add_parser("list", help="List seeded abbreviations.")
    list_parser.add_argument("--all", action="store_true", help="List all rows in abbreviation table.")

    clear_parser = subparsers.add_parser("clear", help="Delete abbreviation seed rows.")
    clear_parser.add_argument("--force", action="store_true", help="Required to allow deletion.")
    clear_parser.add_argument("--dry-run", action="store_true", help="Preview deletions without mutating data.")

    return parser


def _row_to_dict(row: DocumentTypeAbbreviation) -> dict[str, Any]:
    return {
        "document_type": row.document_type,
        "abbreviation": row.abbreviation,
        "is_active": row.is_active,
    }


async def _compute_seed_plan(session) -> tuple[dict[str, DocumentTypeAbbreviation], list[dict[str, Any]]]:
    document_types = [row["document_type"] for row in ABBREVIATION_SEED_ROWS]
    existing_rows = (
        await session.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type.in_(document_types)
            )
        )
    ).scalars().all()
    existing_by_type = {row.document_type: row for row in existing_rows}

    plan: list[dict[str, Any]] = []
    for row in ABBREVIATION_SEED_ROWS:
        existing = existing_by_type.get(row["document_type"])
        if existing is None:
            plan.append({"action": "insert", "row": row})
            continue

        if (
            existing.abbreviation != row["abbreviation"]
            or bool(existing.is_active) != bool(row["is_active"])
        ):
            plan.append({"action": "update", "row": row})
        else:
            plan.append({"action": "skip", "row": row})

    return existing_by_type, plan


async def seed_abbreviations(session, *, dry_run: bool = False) -> dict[str, Any]:
    existing_by_type, plan = await _compute_seed_plan(session)
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
                        DocumentTypeAbbreviation(
                            document_type=row["document_type"],
                            abbreviation=row["abbreviation"],
                            is_active=row["is_active"],
                        )
                    )
                elif action == "update":
                    existing = existing_by_type[row["document_type"]]
                    existing.abbreviation = row["abbreviation"]
                    existing.is_active = row["is_active"]
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
            {"action": item["action"], "document_type": item["row"]["document_type"]}
            for item in plan
        ],
    }


async def list_abbreviations(session, *, list_all: bool = False) -> dict[str, Any]:
    stmt = select(DocumentTypeAbbreviation)
    if not list_all:
        document_types = [row["document_type"] for row in ABBREVIATION_SEED_ROWS]
        stmt = stmt.where(DocumentTypeAbbreviation.document_type.in_(document_types))
    rows = (await session.execute(stmt.order_by(DocumentTypeAbbreviation.document_type.asc()))).scalars().all()
    return {
        "command": "list",
        "count": len(rows),
        "rows": [_row_to_dict(row) for row in rows],
    }


async def clear_abbreviations(session, *, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    document_types = [row["document_type"] for row in ABBREVIATION_SEED_ROWS]
    existing_rows = (
        await session.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type.in_(document_types)
            )
        )
    ).scalars().all()
    existing_types = sorted(row.document_type for row in existing_rows)

    if not force:
        return {
            "command": "clear",
            "dry_run": dry_run,
            "deleted": 0,
            "force_required": True,
            "message": "No-op. Re-run with --force to delete seed rows.",
            "target_document_types_found": existing_types,
        }

    if dry_run:
        return {
            "command": "clear",
            "dry_run": True,
            "deleted": len(existing_types),
            "target_document_types_found": existing_types,
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
        "deleted": len(existing_types),
        "target_document_types_found": existing_types,
    }


async def _run_command(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as session:
        if args.command == "seed":
            result = await seed_abbreviations(session, dry_run=args.dry_run)
        elif args.command == "list":
            result = await list_abbreviations(session, list_all=args.all)
        elif args.command == "clear":
            result = await clear_abbreviations(session, force=args.force, dry_run=args.dry_run)
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

