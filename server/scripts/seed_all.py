#!/usr/bin/env python3
"""Run workflow orchestrator seed scripts in dependency order."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))

from app.db.database import AsyncSessionLocal
from scripts.seed_content_products import clear_content_products, list_content_products, seed_content_products
from scripts.seed_document_type_abbreviations import (
    clear_abbreviations,
    list_abbreviations,
    seed_abbreviations,
)
from scripts.seed_workflows import clear_workflows, list_workflows, seed_workflows


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run all workflow_orchestrator seed scripts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Run all seed scripts in order.")
    seed_parser.add_argument("--dry-run", action="store_true", help="Preview changes without mutating data.")

    list_parser = subparsers.add_parser("list", help="List all targeted seed rows.")
    list_parser.add_argument("--all", action="store_true", help="List all rows for all target tables.")

    clear_parser = subparsers.add_parser("clear", help="Clear all seeded rows in reverse dependency order.")
    clear_parser.add_argument("--force", action="store_true", help="Required to allow deletion.")
    clear_parser.add_argument("--dry-run", action="store_true", help="Preview deletions without mutating data.")

    return parser


async def _run_seed(*, dry_run: bool) -> dict:
    result = {"command": "seed", "dry_run": dry_run, "steps": []}

    async with AsyncSessionLocal() as session:
        result["steps"].append(await seed_workflows(session, dry_run=dry_run))
    async with AsyncSessionLocal() as session:
        result["steps"].append(await seed_abbreviations(session, dry_run=dry_run))
    async with AsyncSessionLocal() as session:
        result["steps"].append(await seed_content_products(session, dry_run=dry_run))

    return result


async def _run_list(*, list_all: bool) -> dict:
    result = {"command": "list", "all": list_all, "steps": []}

    async with AsyncSessionLocal() as session:
        result["steps"].append(await list_workflows(session, list_all=list_all))
    async with AsyncSessionLocal() as session:
        result["steps"].append(await list_abbreviations(session, list_all=list_all))
    async with AsyncSessionLocal() as session:
        result["steps"].append(await list_content_products(session, list_all=list_all))

    return result


async def _run_clear(*, force: bool, dry_run: bool) -> dict:
    result = {"command": "clear", "dry_run": dry_run, "force": force, "steps": []}

    async with AsyncSessionLocal() as session:
        result["steps"].append(await clear_content_products(session, force=force, dry_run=dry_run))
    async with AsyncSessionLocal() as session:
        result["steps"].append(await clear_abbreviations(session, force=force, dry_run=dry_run))
    async with AsyncSessionLocal() as session:
        result["steps"].append(await clear_workflows(session, force=force, dry_run=dry_run))

    return result


async def _run_command(args: argparse.Namespace) -> int:
    if args.command == "seed":
        result = await _run_seed(dry_run=args.dry_run)
    elif args.command == "list":
        result = await _run_list(list_all=args.all)
    elif args.command == "clear":
        result = await _run_clear(force=args.force, dry_run=args.dry_run)
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

