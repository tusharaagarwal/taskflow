"""Add document type abbreviations table and report ID sequence

Revision ID: 005
Revises: 004
Create Date: 2026-02-03 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '005_abbrev'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    """Create document_type_abbreviations table and report_id_seq sequence."""
    
    # Create the document_type_abbreviations table
    op.create_table(
        'document_type_abbreviations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_type', sa.String(100), nullable=False),
        sa.Column('abbreviation', sa.String(10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Create unique index on document_type
    op.create_index(
        'idx_document_type_abbreviations_document_type',
        'document_type_abbreviations',
        ['document_type'],
        unique=True
    )
    
    # Create index on is_active for filtering
    op.create_index(
        'idx_document_type_abbreviations_is_active',
        'document_type_abbreviations',
        ['is_active']
    )
    
    # Create PostgreSQL sequence for report ID generation starting from 100001
    op.execute('CREATE SEQUENCE IF NOT EXISTS report_id_seq START WITH 100001;')


def downgrade():
    """Remove document_type_abbreviations table and report_id_seq sequence."""
    
    # Drop the sequence
    op.execute('DROP SEQUENCE IF EXISTS report_id_seq;')
    
    # Drop indexes
    op.drop_index('idx_document_type_abbreviations_is_active', table_name='document_type_abbreviations')
    op.drop_index('idx_document_type_abbreviations_document_type', table_name='document_type_abbreviations')
    
    # Drop the table
    op.drop_table('document_type_abbreviations')
