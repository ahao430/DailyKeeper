"""add agent execution lane (needs_agent, assigned_agent_id)

Revision ID: b7d8e9f0a1b2
Revises: a1c2f3d4e5f6
Create Date: 2026-11-06

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b7d8e9f0a1b2"
down_revision = "a1c2f3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_executions") as batch:
        batch.add_column(
            sa.Column("needs_agent", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("assigned_agent_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_task_executions_agent", "agents", ["assigned_agent_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("task_executions") as batch:
        batch.drop_constraint("fk_task_executions_agent", type_="foreignkey")
        batch.drop_column("assigned_agent_id")
        batch.drop_column("needs_agent")
