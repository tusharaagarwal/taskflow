"""Initial schema with timestamps for content_product and report_tracker

Revision ID: 001
Revises: 
Create Date: 2023-10-30 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create content_product table with timestamps
    op.create_table(
        'content_product',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=False, index=True),
        sa.Column('created_ts', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column('updated_ts', sa.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for content_product
    op.create_index('ix_content_product_created_ts', 'content_product', ['created_ts'], unique=False)
    
    # Create report_tracker table with timestamps
    op.create_table(
        'report_tracker',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.String(), unique=True, index=True, nullable=False),
        sa.Column('workflow_json', sa.JSON(), nullable=True),
        sa.Column('workflow_steps_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create workflow table without timestamps (temporary)
    op.create_table(
        'workflow',
        sa.Column('workflow_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('workflow_json', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('workflow_id'),
        schema='public'
    )

def downgrade():
    # Drop tables in reverse order
    op.drop_table('report_tracker')
    op.drop_table('content_product')
    op.drop_table('workflow', schema='public')
