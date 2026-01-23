"""Add workflow id=2 seed data

Revision ID: 002
Revises: 001
Create Date: 2026-01-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

# Workflow JSON data for workflow_id = 2
WORKFLOW_JSON = """{"id": "workflow_001", "sla": {"max_days": 30, "on_breach": ["notify_manager"]}, "steps": [{"sla": {"max_hrs": 1, "on_breach": ["notify_lead_author"]}, "actor": {"id": "content_assembler", "pool": false, "role": "NA", "type": "agent"}, "step_id": "initial_draft_001", "step_name": "Assemble Draft", "stage_name": "Authoring", "is_optional": false, "transitions": {"fail_goto": "NA", "success_goto": "initial_draft_002"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": true, "role": "gcc_associate", "type": "human"}, "step_id": "initial_draft_002", "step_name": "Initial Draft", "stage_name": "Authoring", "is_optional": false, "transitions": {"fail_goto": "initial_draft_001", "success_goto": "final_draft"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": false, "role": "research_associate", "type": "human"}, "step_id": "final_draft", "step_name": "Final Draft", "stage_name": "Content Assembly", "is_optional": false, "transitions": {"fail_goto": "initial_draft_002", "success_goto": "copy_editing"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": true, "role": "copy_editor", "type": "human"}, "step_id": "copy_editing", "step_name": "Copy Editing", "stage_name": "Editing", "is_optional": false, "transitions": {"fail_goto": "final_draft", "success_goto": "finalize_report_pre_approval"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": false, "role": "lead_author", "type": "human"}, "step_id": "finalize_report_pre_approval", "step_name": "Finalize Report", "stage_name": "Finalization", "is_optional": false, "transitions": {"fail_goto": "copy_editing", "success_goto": "l1_approval"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author", "notify_manager"]}, "actor": {"pool": true, "role": "internal_reviewer", "type": "human"}, "step_id": "l1_approval", "step_name": "L1 Approval", "stage_name": "Internal Review", "is_optional": false, "transitions": {"fail_goto": "finalize_report_post_rejection", "success_goto": "l2_approval"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author", "notify_manager"]}, "actor": {"pool": false, "role": "internal_reviewer", "type": "human"}, "step_id": "l2_approval", "step_name": "L2 Approval", "stage_name": "Internal Review", "is_optional": false, "transitions": {"fail_goto": "finalize_report_post_rejection", "success_goto": "l3_approval"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author", "notify_manager"]}, "actor": {"pool": true, "role": "internal_reviewer", "type": "human"}, "step_id": "l3_approval", "step_name": "L3 Approval", "stage_name": "Internal Review", "is_optional": false, "transitions": {"fail_goto": "finalize_report_post_rejection", "success_goto": "l4_approval"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author", "notify_manager"]}, "actor": {"pool": false, "role": "internal_reviewer", "type": "human"}, "step_id": "l4_approval", "step_name": "L4 Approval", "stage_name": "Internal Review", "is_optional": false, "transitions": {"fail_goto": "finalize_report_post_rejection", "success_goto": "external_review"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": true, "role": "lead_author", "type": "human"}, "step_id": "finalize_report_post_rejection", "step_name": "Finalize Report", "stage_name": "Internal Review", "is_optional": false, "transitions": {"fail_goto": "NA", "success_goto": "l1_approval"}}, {"sla": {"max_hrs": 72, "on_breach": ["notify_lead_author", "notify_manager"]}, "actor": {"pool": false, "role": "external_reviewer", "type": "human"}, "step_id": "external_review", "step_name": "External Review", "stage_name": "External Review", "is_optional": false, "transitions": {"fail_goto": "final_review", "success_goto": "publication"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": true, "role": "lead_author", "type": "human"}, "step_id": "final_review", "step_name": "Final Review", "stage_name": "External Review", "is_optional": false, "transitions": {"fail_goto": "NA", "success_goto": "internal_review_post_external"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": false, "role": "lead_author", "type": "human"}, "step_id": "internal_review_post_external", "step_name": "Internal Review", "stage_name": "External Review", "is_optional": false, "transitions": {"fail_goto": "final_review", "success_goto": "publication"}}, {"sla": {"max_hrs": 24, "on_breach": ["notify_lead_author"]}, "actor": {"pool": true, "role": "lead_author", "type": "human"}, "step_id": "publication", "step_name": "Publication", "stage_name": "Publication", "is_optional": false, "transitions": {"fail_goto": "publication", "success_goto": "published"}}, {"sla": {}, "actor": {"pool": false, "role": "lead_author", "type": "human"}, "step_id": "published", "step_name": "Published", "stage_name": "Published", "is_optional": false, "transitions": {"fail_goto": "NA", "success_goto": "NA"}}], "description": "Standard publication workflow", "workflow_name": "Publication Workflow"}"""


def upgrade():
    """Insert workflow record with id=2"""
    # Escape single quotes in the JSON string for PostgreSQL
    escaped_json = WORKFLOW_JSON.replace("'", "''")
    
    # Check if record already exists and insert only if it doesn't (idempotent)
    op.execute(f"""
        INSERT INTO public.workflow (workflow_id, workflow_json)
        SELECT 2, '{escaped_json}'
        WHERE NOT EXISTS (
            SELECT 1 FROM public.workflow WHERE workflow_id = 2
        );
    """)


def downgrade():
    """Remove workflow record with id=2"""
    op.execute("DELETE FROM public.workflow WHERE workflow_id = 2;")

