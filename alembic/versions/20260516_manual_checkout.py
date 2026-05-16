"""Add manual checkout, shipping rules, and production metadata.

Revision ID: 20260516_manual_checkout
Revises: 20251207_batch_uploads
Create Date: 2026-05-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260516_manual_checkout"
down_revision = "20251207_batch_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("production_type", sa.String(length=30), nullable=False, server_default="in_stock"))
    op.add_column("products", sa.Column("material", sa.String(), nullable=True))
    op.add_column("products", sa.Column("color", sa.String(), nullable=True))
    op.add_column("products", sa.Column("scale", sa.String(), nullable=True))
    op.add_column("products", sa.Column("estimated_production_days", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("requires_manual_review", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("products", sa.Column("weight_grams", sa.Integer(), nullable=True))

    op.add_column("orders", sa.Column("subtotal", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("shipping_cost", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("payment_method", sa.String(length=30), nullable=False, server_default="bizum"))
    op.add_column("orders", sa.Column("payment_status", sa.String(length=30), nullable=False, server_default="PENDING"))
    op.add_column("orders", sa.Column("payment_reference", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("payment_instructions", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("paid_at", sa.DateTime(), nullable=True))
    op.add_column("orders", sa.Column("phone", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("customer_notes", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("admin_notes", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("tracking_number", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipping_carrier", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipped_at", sa.DateTime(), nullable=True))

    op.create_table(
        "order_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_order_attachments_order", "order_attachments", ["order_id"])

    op.create_table(
        "shipping_rate_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("postal_prefix", sa.String(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("base_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("per_item_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("per_kg_cost", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("free_shipping_min_subtotal", sa.Numeric(10, 2), nullable=True),
        sa.Column("estimated_delivery_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_shipping_rules_lookup", "shipping_rate_rules", ["country_code", "postal_prefix", "is_active"])

    op.execute("UPDATE orders SET subtotal = total_cost WHERE subtotal = 0")

    op.alter_column("products", "production_type", server_default=None)
    op.alter_column("products", "requires_manual_review", server_default=None)
    op.alter_column("orders", "subtotal", server_default=None)
    op.alter_column("orders", "shipping_cost", server_default=None)
    op.alter_column("orders", "payment_method", server_default=None)
    op.alter_column("orders", "payment_status", server_default=None)
    op.alter_column("shipping_rate_rules", "currency", server_default=None)
    op.alter_column("shipping_rate_rules", "base_cost", server_default=None)
    op.alter_column("shipping_rate_rules", "per_item_cost", server_default=None)
    op.alter_column("shipping_rate_rules", "per_kg_cost", server_default=None)
    op.alter_column("shipping_rate_rules", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_shipping_rules_lookup", table_name="shipping_rate_rules")
    op.drop_table("shipping_rate_rules")

    op.drop_index("ix_order_attachments_order", table_name="order_attachments")
    op.drop_table("order_attachments")

    op.drop_column("orders", "shipped_at")
    op.drop_column("orders", "shipping_carrier")
    op.drop_column("orders", "tracking_number")
    op.drop_column("orders", "admin_notes")
    op.drop_column("orders", "customer_notes")
    op.drop_column("orders", "phone")
    op.drop_column("orders", "paid_at")
    op.drop_column("orders", "payment_instructions")
    op.drop_column("orders", "payment_reference")
    op.drop_column("orders", "payment_status")
    op.drop_column("orders", "payment_method")
    op.drop_column("orders", "shipping_cost")
    op.drop_column("orders", "subtotal")

    op.drop_column("products", "weight_grams")
    op.drop_column("products", "requires_manual_review")
    op.drop_column("products", "estimated_production_days")
    op.drop_column("products", "scale")
    op.drop_column("products", "color")
    op.drop_column("products", "material")
    op.drop_column("products", "production_type")
