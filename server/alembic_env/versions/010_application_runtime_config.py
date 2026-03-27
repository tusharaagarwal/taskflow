"""Singleton application_runtime_config table with JSONB data map

Revision ID: 010
Revises: 009
Create Date: 2026-03-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_runtime_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO application_runtime_config (id, data)
        SELECT 1, '{}'::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM application_runtime_config WHERE id = 1)
        """
    )


def downgrade():
    op.drop_table("application_runtime_config")
