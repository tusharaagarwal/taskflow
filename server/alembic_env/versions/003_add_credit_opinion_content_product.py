"""Add Credit Opinion content product seed data

Revision ID: 003
Revises: 002
Create Date: 2026-01-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Insert Credit Opinion content product record"""
    # Check if record already exists and insert only if it doesn't (idempotent)
    op.execute("""
        INSERT INTO public.content_product (id, name, workflow_id, created_ts, updated_ts)
        SELECT 1, 'Credit Opinion', 2, NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM public.content_product WHERE id = 1
        );
    """)
    
    # Reset the sequence if needed (in case id=1 is inserted manually)
    op.execute("""
        SELECT setval('content_product_id_seq', 
            GREATEST((SELECT MAX(id) FROM public.content_product), 1), 
            true
        );
    """)


def downgrade():
    """Remove Credit Opinion content product record"""
    op.execute("""
        DELETE FROM public.content_product 
        WHERE id = 1 AND name = 'Credit Opinion' AND workflow_id = 2;
    """)
