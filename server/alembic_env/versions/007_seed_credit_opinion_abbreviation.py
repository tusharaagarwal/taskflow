"""Seed abbreviation data for Credit Opinion

Revision ID: 007
Revises: 006
Create Date: 2026-02-03 23:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
import uuid

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None

# Define the table structure for seeding
abbr_table = table(
    'document_type_abbreviations',
    column('id', sa.dialects.postgresql.UUID),
    column('document_type', sa.String),
    column('abbreviation', sa.String),
    column('is_active', sa.Boolean)
)

def upgrade():
    """Seed the Credit Opinion abbreviation."""
    op.bulk_insert(
        abbr_table,
        [
            {
                'id': str(uuid.uuid4()),
                'document_type': 'Credit Opinion',
                'abbreviation': 'CO',
                'is_active': True
            }
        ]
    )


def downgrade():
    """Remove the seeded Credit Opinion abbreviation."""
    op.execute("DELETE FROM document_type_abbreviations WHERE document_type = 'Credit Opinion'")
