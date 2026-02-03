"""Add transaction_id, pr_id, cpm_id, and action_code fields to report_tracker

Revision ID: 006
Revises: 005
Create Date: 2026-02-03 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    """Add transaction_id, pr_id, cpm_id, and action_code columns to report_tracker table."""
    
    # Add new columns
    op.add_column('report_tracker', sa.Column('transaction_id', sa.String(), nullable=True))
    op.add_column('report_tracker', sa.Column('pr_id', sa.String(), nullable=True))
    op.add_column('report_tracker', sa.Column('cpm_id', sa.String(), nullable=True))
    op.add_column('report_tracker', sa.Column('action_code', sa.String(), nullable=True))
    
    # Create indexes for performance
    op.create_index('idx_report_tracker_transaction_id', 'report_tracker', ['transaction_id'])
    op.create_index('idx_report_tracker_pr_id', 'report_tracker', ['pr_id'])


def downgrade():
    """Remove transaction_id, pr_id, cpm_id, and action_code columns."""
    
    # Drop indexes
    op.drop_index('idx_report_tracker_pr_id', table_name='report_tracker')
    op.drop_index('idx_report_tracker_transaction_id', table_name='report_tracker')
    
    # Drop columns
    op.drop_column('report_tracker', 'action_code')
    op.drop_column('report_tracker', 'cpm_id')
    op.drop_column('report_tracker', 'pr_id')
    op.drop_column('report_tracker', 'transaction_id')
