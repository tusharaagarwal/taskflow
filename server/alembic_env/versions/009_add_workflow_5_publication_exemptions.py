"""Add workflow id=5 Publication Workflow with Exemptions

Revision ID: 009
Revises: 008
Create Date: 2026-03-08 00:00:00.000000

Inserts new workflow row (workflow_id=5) with Publication Workflow with Exemptions JSON.
All existing data (workflow 3, 4, etc.) remains unchanged.
"""
from alembic import op
from sqlalchemy import text

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

WORKFLOW_JSON = r'{"id":"workflow_002","workflow_name":"Publication Workflow (Exemptions)","description":"Publication workflow with ERRC exemption routing per General CO Workflow specification. 13 steps including ERRC Exemption Review (Stage 7) with conditional L1 routing.","sla":{"max_days":30,"on_breach":["notify_manager"]},"steps":[{"step_id":"assembly","step_name":"Assembly","stage_name":"Assembly","actor":{"id":"content_assembler","pool":false,"role":[],"type":"agent"},"is_optional":false,"sla":{"max_hrs":1,"on_breach":["notify_platform_admin"]},"transitions":{"success_goto":"initial_draft","fail_goto":"NA"}},{"step_id":"initial_draft","step_name":"Initial Draft","stage_name":"Authoring","actor":{"pool":true,"role":["gcc_associate"],"type":"human"},"is_optional":false,"sla":{"max_hrs":24,"on_breach":["notify_lead_author"]},"transitions":{"success_goto":"final_draft","fail_goto":"NA"}},{"step_id":"final_draft","step_name":"Final Draft","stage_name":"Authoring","actor":{"pool":false,"role":["ratings_associate"],"type":"human"},"is_optional":false,"sla":{"max_hrs":24,"on_breach":["notify_lead_author"]},"transitions":{"success_goto":"copy_editing","fail_goto":"initial_draft"}},{"step_id":"copy_editing","step_name":"Copy Editing","stage_name":"Editing","actor":{"pool":true,"role":["copy_editor"],"type":"human"},"is_optional":true,"sla":{"max_hrs":24,"on_breach":["notify_lead_author"]},"transitions":{"success_goto":"finalize_report","fail_goto":"final_draft"}},{"step_id":"finalize_report","step_name":"Finalize Report","stage_name":"Finalization","actor":{"pool":false,"role":["lead_author"],"type":"human"},"is_optional":false,"sla":{"max_hrs":24,"on_breach":["notify_lead_author"]},"transitions":{"success_goto":"internal_review_l1","fail_goto":"final_draft"}},{"step_id":"internal_review_l1","step_name":"Internal Review (L1)","stage_name":"Review","actor":{"pool":false,"role":["internal_reviewer_l1"],"type":"human"},"is_optional":false,"sla":{"max_hrs":24,"on_breach":["notify_lead_author","notify_manager"]},"transitions":{"success_goto":{"default":"pre_publication_review","no_exemption":"pre_publication_review","from_reapproval":"in_publication","exception":{"errc":{"approved":"errc_review","rejected":"pre_publication_review"},"non_errc":{"approved":"in_publication","rejected":"pre_publication_review"}}},"fail_goto":{"default":"finalize_report","from_reapproval":"internal_final_review"}}},{"step_id":"errc_review","step_name":"ERRC Exemption Review","stage_name":"Review","actor":{"pool":false,"role":["errc_reviewer"],"type":"human"},"is_optional":true,"sla":{"max_hrs":24,"on_breach":["notify_lead_author"]},"transitions":{"success_goto":{"default":"pre_publication_review","approved":"in_publication"},"fail_goto":"NA"}},{"step_id":"pre_publication_review","step_name":"Pre-Publication Review","stage_name":"Review","actor":{"pool":false,"role":["issuer"],"type":"human"},"is_optional":true,"sla":{"max_hrs":72,"on_breach":["notify_lead_author","notify_manager"]},"transitions":{"success_goto":{"default":"internal_final_review","accepted":"in_publication"},"fail_goto":"NA"}},{"step_id":"internal_final_review","step_name":"Internal Final Review","stage_name":"Review","actor":{"pool":false,"role":["lead_author"],"type":"human"},"is_optional":true,"sla":{"max_hrs":24,"on_breach":["notify_lead_author"]},"transitions":{"success_goto":"in_publication","fail_goto":"internal_review_l1"}},{"step_id":"in_publication","step_name":"In Publication","stage_name":"Publication","actor":{"pool":false,"role":[],"type":"system"},"is_optional":false,"sla":{"max_hrs":24,"on_breach":["notify_platform_admin","notify_lead_author"]},"transitions":{"success_goto":"published","fail_goto":"RETRY"}},{"step_id":"published","step_name":"Published","stage_name":"Published","actor":{"pool":false,"role":[],"type":"system"},"is_optional":false,"sla":{},"transitions":{"success_goto":"NA","fail_goto":{"default":"NA","unpublish":"unpublish_in_progress","republish":"internal_final_review"}}},{"step_id":"unpublish_in_progress","step_name":"Un-Publish (In-Progress)","stage_name":"Un-Publish","actor":{"pool":false,"role":["lead_author","platform_admin","internal_reviewer_l1"],"type":"human"},"is_optional":true,"sla":{"max_hrs":24,"on_breach":["notify_platform_admin","notify_lead_author"]},"transitions":{"success_goto":"unpublished","fail_goto":"RETRY"}},{"step_id":"unpublished","step_name":"Un-Published","stage_name":"Un-Publish","actor":{"pool":false,"role":[],"type":"system"},"is_optional":true,"sla":{},"transitions":{"success_goto":"internal_final_review","fail_goto":"NA"}}]}'


def upgrade():
    conn = op.get_bind()
    conn.execute(
        text("""
            INSERT INTO public.workflow (workflow_id, workflow_json, name)
            SELECT :workflow_id, :workflow_json, :name
            WHERE NOT EXISTS (SELECT 1 FROM public.workflow WHERE workflow_id = :workflow_id)
        """),
        {
            "workflow_id": 5,
            "workflow_json": WORKFLOW_JSON,
            "name": "Publication Workflow with Exemptions",
        },
    )


def downgrade():
    op.execute("DELETE FROM public.workflow WHERE workflow_id = 5;")

