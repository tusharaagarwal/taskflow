#!/usr/bin/env python3
"""
Database Migration Runner for Alembic

This script runs Alembic migrations in AWS ECS environment.
It's designed to be run as a one-off ECS task before deploying the application.

Usage:
    python scripts/run_migrations.py

Exit Codes:
    0 - Success
    1 - Failure
"""
import sys
import os
from pathlib import Path

# Add parent directory to Python path so we can import our modules
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

from alembic import command
from alembic.config import Config


def run_migrations():
    """
    Run all pending Alembic migrations.
    
    This function:
    1. Loads Alembic configuration
    2. Shows current database revision
    3. Runs all pending migrations to HEAD
    4. Shows final database revision
    
    Returns:
        int: 0 if successful, 1 if failed
    """
    try:
        # Set up Alembic configuration
        base_dir = Path(__file__).resolve().parent.parent
        alembic_ini_path = base_dir / "alembic.ini"
        
        if not alembic_ini_path.exists():
            print(f"❌ Error: alembic.ini not found at {alembic_ini_path}")
            return 1
        
        # Create Alembic config object
        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("script_location", str(base_dir / "alembic_env"))
        
        print("=" * 70)
        print("🗄️  DATABASE MIGRATION RUNNER - Workflow Orchestrator")
        print("=" * 70)
        
        # Show current database revision
        print("\n📊 Checking current database state...")
        try:
            command.current(alembic_cfg, verbose=True)
        except Exception as e:
            print(f"ℹ️  Database not initialized yet (this is normal for first run)")
            print(f"   Details: {e}")
        
        # Run migrations
        print("\n🚀 Running migrations to HEAD...")
        print("-" * 70)
        command.upgrade(alembic_cfg, "head")
        
        # Show final revision
        print("\n✅ Migrations completed successfully!")
        print("-" * 70)
        print("📊 Current database revision:")
        command.current(alembic_cfg, verbose=True)
        
        print("\n" + "=" * 70)
        print("✅ DATABASE MIGRATION COMPLETED")
        print("=" * 70)
        
        return 0
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ MIGRATION FAILED")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print("\nFull traceback:")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = run_migrations()
    sys.exit(exit_code)
