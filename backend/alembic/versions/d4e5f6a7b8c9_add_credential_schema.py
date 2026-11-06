"""add credential_schema to platforms (plugin-declared credential fields)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-06

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("platforms") as batch:
        batch.add_column(sa.Column("credential_schema", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("platforms") as batch:
        batch.drop_column("credential_schema")
