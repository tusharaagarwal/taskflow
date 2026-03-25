"""Fix status column from ENUM to VARCHAR

Revision ID: 002
Revises: 001
Create Date: 2026-03-25 17:52:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # First, drop the index that depends on the enum column
    op.drop_index('ix_tasks_status', 'tasks')

    # Then recreate the tasks table with VARCHAR instead of ENUM
    op.create_table(
        'tasks_new',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), server_default='todo', nullable=False),
        sa.Column('priority', sa.Integer, server_default='2', nullable=False),
        sa.Column('due_date', sa.DateTime, nullable=True),
        sa.Column('owner_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Copy data from old table to new table
    op.execute("""
        INSERT INTO tasks_new (id, title, description, status, priority, due_date, owner_id, created_at, updated_at)
        SELECT id, title, description, status, priority, due_date, owner_id, created_at, updated_at
        FROM tasks
    """)

    # Drop old table
    op.drop_table('tasks')

    # Rename new table to tasks
    op.execute('ALTER TABLE tasks_new RENAME TO tasks')

    # Drop the enum type (now that no table depends on it)
    op.execute('DROP TYPE IF EXISTS taskstatus')

    # Recreate index
    op.create_index('ix_tasks_owner_id', 'tasks', ['owner_id'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])

def downgrade() -> None:
    # This would require recreating the original state
    # For simplicity, we'll just recreate the original table structure
    op.execute('DROP TABLE IF EXISTS tasks')

    # Recreate taskstatus enum type
    op.execute("CREATE TYPE taskstatus AS ENUM ('todo', 'in_progress', 'done', 'archived')")

    # Recreate tasks table with enum
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', postgresql.ENUM('todo', 'in_progress', 'done', 'archived', name='taskstatus'), server_default='todo', nullable=False),
        sa.Column('priority', sa.Integer, server_default='2', nullable=False),
        sa.Column('due_date', sa.DateTime, nullable=True),
        sa.Column('owner_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_index('ix_tasks_owner_id', 'tasks', ['owner_id'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])
