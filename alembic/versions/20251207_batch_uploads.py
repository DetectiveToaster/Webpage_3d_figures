"""Add product status, media ordering/path, and upload sessions.

Revision ID: 20251207_batch_uploads
Revises: 20251206_order_enhancements
Create Date: 2025-12-07 00:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251207_batch_uploads"
down_revision = "20251206_order_enhancements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Products: add status
    op.add_column("products", sa.Column("status", sa.String(length=20), nullable=False, server_default="published"))

    # Product media: ordering and optional path
    op.add_column("product_media", sa.Column("path", sa.Text(), nullable=True))
    op.add_column("product_media", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

    # Upload session staging tables
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "upload_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("upload_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_upload_files_session", "upload_files", ["session_id"])

    # Drop server defaults after data backfill
    op.alter_column("products", "status", server_default=None)
    op.alter_column("product_media", "sort_order", server_default=None)
    op.alter_column("upload_files", "sort_order", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_upload_files_session", table_name="upload_files")
    op.drop_table("upload_files")
    op.drop_table("upload_sessions")

    op.drop_column("product_media", "sort_order")
    op.drop_column("product_media", "path")
    op.drop_column("products", "status")
