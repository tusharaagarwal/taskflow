#!/usr/bin/env python3
"""Seed workflows with guarded, idempotent operations."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))

from app.db.database import AsyncSessionLocal
from app.seed_data.workflow_seed_data import WORKFLOW_SEED_ROWS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed workflow table data safely.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Insert/update workflow seed rows.")
    seed_parser.add_argument("--dry-run", action="store_true", help="Preview changes without mutating data.")

    list_parser = subparsers.add_parser("list", help="List seeded workflow rows.")
    list_parser.add_argument("--all", action="store_true", help="List all rows in workflow table.")

    clear_parser = subparsers.add_parser("clear", help="Delete workflow seed rows.")
    clear_parser.add_argument("--force", action="store_true", help="Required to allow deletion.")
    clear_parser.add_argument("--dry-run", action="store_true", help="Preview deletions without mutating data.")

    return parser


def _table_name_for_session(session) -> str:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        return "public.workflow"
    return "workflow"


async def _workflow_columns(session) -> set[str]:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        query = text(
            """
            select column_name
            from information_schema.columns
            where table_schema='public' and table_name='workflow'
            """
        )
        rows = (await session.execute(query)).fetchall()
        return {row[0] for row in rows}

    pragma_rows = (await session.execute(text("PRAGMA table_info(workflow)"))).fetchall()
    return {row[1] for row in pragma_rows}


def _id_list_sql(ids: list[int]) -> str:
    return ",".join(str(item) for item in ids)


async def _existing_rows_by_id(session, target_ids: list[int]) -> dict[int, dict[str, Any]]:
    columns = await _workflow_columns(session)
    has_name = "name" in columns
    has_is_active = "is_active" in columns
    table_name = _table_name_for_session(session)

    name_select = "name" if has_name else "''::text as name"
    active_select = "is_active" if has_is_active else "true as is_active"
    if table_name == "workflow":
        name_select = "name" if has_name else "'' as name"
        active_select = "is_active" if has_is_active else "1 as is_active"

    query = text(
        f"""
        select workflow_id, workflow_json, {name_select}, {active_select}
        from {table_name}
        where workflow_id in ({_id_list_sql(target_ids)})
        """
    )
    rows = (await session.execute(query)).fetchall()
    return {
        int(row[0]): {
            "workflow_id": int(row[0]),
            "workflow_json": row[1],
            "name": row[2] or "",
            "is_active": bool(row[3]),
        }
        for row in rows
    }


async def seed_workflows(session, *, dry_run: bool = False) -> dict[str, Any]:
    target_ids = [row["workflow_id"] for row in WORKFLOW_SEED_ROWS]
    existing_by_id = await _existing_rows_by_id(session, target_ids)
    columns = await _workflow_columns(session)
    has_name = "name" in columns
    has_is_active = "is_active" in columns
    table_name = _table_name_for_session(session)

    inserted = 0
    updated = 0
    skipped = 0
    planned_actions: list[dict[str, Any]] = []

    for row in WORKFLOW_SEED_ROWS:
        existing = existing_by_id.get(row["workflow_id"])
        if existing is None:
            planned_actions.append({"action": "insert", "workflow_id": row["workflow_id"]})
            inserted += 1
            continue

        should_update = existing["workflow_json"] != row["workflow_json"]
        if has_name:
            should_update = should_update or (existing["name"] != row["name"])
        if has_is_active:
            should_update = should_update or (bool(existing["is_active"]) != bool(row["is_active"]))
        if should_update:
            planned_actions.append({"action": "update", "workflow_id": row["workflow_id"]})
            updated += 1
        else:
            skipped += 1

    if not dry_run:
        try:
            for row in WORKFLOW_SEED_ROWS:
                existing = existing_by_id.get(row["workflow_id"])
                if existing is None:
                    if has_name and has_is_active:
                        await session.execute(
                            text(
                                f"""
                                insert into {table_name} (workflow_id, workflow_json, name, is_active)
                                values (:workflow_id, :workflow_json, :name, :is_active)
                                """
                            ),
                            row,
                        )
                    else:
                        await session.execute(
                            text(
                                f"""
                                insert into {table_name} (workflow_id, workflow_json)
                                values (:workflow_id, :workflow_json)
                                """
                            ),
                            {"workflow_id": row["workflow_id"], "workflow_json": row["workflow_json"]},
                        )
                    continue

                should_update = existing["workflow_json"] != row["workflow_json"]
                if has_name:
                    should_update = should_update or (existing["name"] != row["name"])
                if has_is_active:
                    should_update = should_update or (bool(existing["is_active"]) != bool(row["is_active"]))
                if should_update:
                    if has_name and has_is_active:
                        await session.execute(
                            text(
                                f"""
                                update {table_name}
                                set workflow_json=:workflow_json, name=:name, is_active=:is_active
                                where workflow_id=:workflow_id
                                """
                            ),
                            row,
                        )
                    else:
                        await session.execute(
                            text(
                                f"""
                                update {table_name}
                                set workflow_json=:workflow_json
                                where workflow_id=:workflow_id
                                """
                            ),
                            {"workflow_id": row["workflow_id"], "workflow_json": row["workflow_json"]},
                        )
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
        "planned_actions": planned_actions,
    }


async def list_workflows(session, *, list_all: bool = False) -> dict[str, Any]:
    columns = await _workflow_columns(session)
    has_name = "name" in columns
    has_is_active = "is_active" in columns
    table_name = _table_name_for_session(session)
    name_select = "name" if has_name else "''::text as name"
    active_select = "is_active" if has_is_active else "true as is_active"
    if table_name == "workflow":
        name_select = "name" if has_name else "'' as name"
        active_select = "is_active" if has_is_active else "1 as is_active"

    where_clause = ""
    if not list_all:
        target_ids = [row["workflow_id"] for row in WORKFLOW_SEED_ROWS]
        where_clause = f" where workflow_id in ({_id_list_sql(target_ids)})"

    query = text(
        f"""
        select workflow_id, {name_select}, {active_select}
        from {table_name}
        {where_clause}
        order by workflow_id asc
        """
    )
    rows = (await session.execute(query)).fetchall()
    return {
        "command": "list",
        "count": len(rows),
        "rows": [
            {
                "workflow_id": int(row[0]),
                "name": row[1] or "",
                "is_active": bool(row[2]),
            }
            for row in rows
        ],
    }


async def clear_workflows(session, *, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    target_ids = [row["workflow_id"] for row in WORKFLOW_SEED_ROWS]
    existing = await _existing_rows_by_id(session, target_ids)
    existing_ids = sorted(existing.keys())
    table_name = _table_name_for_session(session)

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
        if existing_ids:
            await session.execute(
                text(f"delete from {table_name} where workflow_id in ({_id_list_sql(existing_ids)})")
            )
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
            result = await seed_workflows(session, dry_run=args.dry_run)
        elif args.command == "list":
            result = await list_workflows(session, list_all=args.all)
        elif args.command == "clear":
            result = await clear_workflows(session, force=args.force, dry_run=args.dry_run)
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

