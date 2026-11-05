"""add needs_browser to task_executions

Revision ID: a1c2f3d4e5f6
Revises: e89e9e33c0c4
Create Date: 2026-11-06

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1c2f3d4e5f6"
down_revision = "e89e9e33c0c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_executions",
        sa.Column("needs_browser", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("task_executions", "needs_browser")
