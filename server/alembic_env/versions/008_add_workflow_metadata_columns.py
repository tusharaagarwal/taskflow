"""Add workflow metadata columns (name, is_active, created_at, updated_at, deleted_at)

Revision ID: 008
Revises: 007
Create Date: 2026-02-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workflow",
        sa.Column("name", sa.String(), nullable=True),
        schema="public",
    )
    op.add_column(
        "workflow",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        schema="public",
    )
    op.add_column(
        "workflow",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        schema="public",
    )
    op.add_column(
        "workflow",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        schema="public",
    )
    op.add_column(
        "workflow",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )

    # Backfill name from workflow_json->>'workflow_name' or workflow_json->>'name' where possible
    op.execute(
        """
        UPDATE public.workflow
        SET name = COALESCE(
            (workflow_json::json)->>'workflow_name',
            (workflow_json::json)->>'name'
        )
        WHERE (workflow_json::json)->>'workflow_name' IS NOT NULL
           OR (workflow_json::json)->>'name' IS NOT NULL;
        """
    )

    op.create_index(
        "ix_workflow_is_active",
        "workflow",
        ["is_active"],
        unique=False,
        schema="public",
    )


def downgrade():
    op.drop_index(
        "ix_workflow_is_active",
        table_name="workflow",
        schema="public",
    )
    op.drop_column("workflow", "deleted_at", schema="public")
    op.drop_column("workflow", "updated_at", schema="public")
    op.drop_column("workflow", "created_at", schema="public")
    op.drop_column("workflow", "is_active", schema="public")
    op.drop_column("workflow", "name", schema="public")
