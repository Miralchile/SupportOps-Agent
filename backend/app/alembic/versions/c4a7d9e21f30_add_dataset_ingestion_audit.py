"""Add dataset ingestion audit and ticket provenance fields.

Revision ID: c4a7d9e21f30
Revises: b7f2c9e4a102
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a7d9e21f30"
down_revision: Union[str, None] = "b7f2c9e4a102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_import_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("dataset_name", sa.String(length=120), nullable=False),
        sa.Column("dataset_version", sa.String(length=80), nullable=False, server_default="unknown"),
        sa.Column("source_filename", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pii_redacted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("split_counts", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dataset_import_jobs_user_id", "dataset_import_jobs", ["user_id"])
    op.create_index("idx_dataset_import_jobs_dataset_name", "dataset_import_jobs", ["dataset_name"])
    op.create_index("idx_dataset_import_jobs_source_type", "dataset_import_jobs", ["source_type"])
    op.create_index("idx_dataset_import_jobs_status", "dataset_import_jobs", ["status"])
    op.create_index(
        "uq_dataset_import_jobs_user_checksum",
        "dataset_import_jobs",
        ["user_id", "dataset_name", "checksum"],
        unique=True,
    )

    op.add_column("tickets", sa.Column("source_type", sa.String(length=32), nullable=False, server_default="unknown"))
    op.add_column("tickets", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.add_column("tickets", sa.Column("conversation_id", sa.String(length=255), nullable=True))
    op.add_column("tickets", sa.Column("language", sa.String(length=16), nullable=False, server_default="unknown"))
    op.add_column("tickets", sa.Column("dataset_split", sa.String(length=16), nullable=False, server_default="unspecified"))
    op.add_column("tickets", sa.Column("raw_category", sa.String(length=255), nullable=True))
    op.add_column("tickets", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("tickets", sa.Column("pii_redacted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("tickets", sa.Column("quality_score", sa.Float(), nullable=False, server_default="1"))
    op.add_column("tickets", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("tickets", sa.Column("import_job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_import_job_id",
        "tickets",
        "dataset_import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_tickets_source_type", "tickets", ["source_type"])
    op.create_index("idx_tickets_conversation_id", "tickets", ["conversation_id"])
    op.create_index("idx_tickets_dataset_split", "tickets", ["dataset_split"])
    op.create_index("idx_tickets_content_hash", "tickets", ["content_hash"])
    op.create_index("idx_tickets_import_job_id", "tickets", ["import_job_id"])
    op.create_index(
        "uq_tickets_user_source_external_id",
        "tickets",
        ["user_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tickets_user_source_external_id", table_name="tickets")
    op.drop_index("idx_tickets_import_job_id", table_name="tickets")
    op.drop_index("idx_tickets_content_hash", table_name="tickets")
    op.drop_index("idx_tickets_dataset_split", table_name="tickets")
    op.drop_index("idx_tickets_conversation_id", table_name="tickets")
    op.drop_index("idx_tickets_source_type", table_name="tickets")
    op.drop_constraint("fk_tickets_import_job_id", "tickets", type_="foreignkey")
    for column in (
        "import_job_id", "content_hash", "quality_score", "pii_redacted", "metadata_json",
        "raw_category", "dataset_split", "language", "conversation_id", "external_id", "source_type",
    ):
        op.drop_column("tickets", column)
    op.drop_index("uq_dataset_import_jobs_user_checksum", table_name="dataset_import_jobs")
    op.drop_index("idx_dataset_import_jobs_status", table_name="dataset_import_jobs")
    op.drop_index("idx_dataset_import_jobs_source_type", table_name="dataset_import_jobs")
    op.drop_index("idx_dataset_import_jobs_dataset_name", table_name="dataset_import_jobs")
    op.drop_index("idx_dataset_import_jobs_user_id", table_name="dataset_import_jobs")
    op.drop_table("dataset_import_jobs")
