"""Fix status column from ENUM to VARCHAR

Revision ID: 002
Revises: 001
Create Date: 2026-03-25 17:46:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Drop the existing taskstatus enum type
    op.execute('DROP TYPE IF EXISTS taskstatus')

    # Alter the tasks table to use VARCHAR instead of ENUM for status
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE VARCHAR(50) USING status::VARCHAR")

def downgrade() -> None:
    # Recreate the taskstatus enum type
    op.execute("CREATE TYPE taskstatus AS ENUM ('todo', 'in_progress', 'done', 'archived')")

    # Change status back to ENUM
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE taskstatus USING status::taskstatus")
