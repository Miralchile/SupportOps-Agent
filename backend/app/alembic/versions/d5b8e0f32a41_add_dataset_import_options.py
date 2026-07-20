"""Add dataset import options.

Revision ID: d5b8e0f32a41
Revises: c4a7d9e21f30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5b8e0f32a41"
down_revision: Union[str, None] = "c4a7d9e21f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_import_jobs",
        sa.Column("import_options", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )


def downgrade() -> None:
    op.drop_column("dataset_import_jobs", "import_options")
