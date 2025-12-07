"""Expand order schema with pricing, shipping, and indexes.

Revision ID: 20251206_order_enhancements
Revises: 6f4b0bdf566f
Create Date: 2025-12-06 14:25:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251206_order_enhancements"
down_revision = "6f4b0bdf566f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Orders: add order number, currency, shipping fields
    op.add_column("orders", sa.Column("order_number", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"))
    op.add_column("orders", sa.Column("shipping_address_line1", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipping_address_line2", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipping_city", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipping_state", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipping_postal_code", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("shipping_country_code", sa.String(length=2), nullable=True))
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
    op.create_index("ix_orders_user_date", "orders", ["user_id", "date"])

    # Order line items: capture pricing and currency
    op.add_column("order_products", sa.Column("unit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("order_products", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column("order_products", sa.Column("line_total", sa.Numeric(10, 2), nullable=True))
    op.create_index("ix_order_products_order", "order_products", ["order_id"])

    # Cart: prevent duplicate product entries per user
    op.create_unique_constraint("uq_cart_user_product", "cart", ["user_id", "product_id"])
    op.create_index("ix_cart_user", "cart", ["user_id"])

    # Products: visibility and recency indexes
    op.create_index("ix_products_visible", "products", ["is_visible"])
    op.create_index("ix_products_created_at", "products", ["created_at"])

    # Cleanup server defaults after data backfill (if any)
    op.alter_column("orders", "currency", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_products_created_at", table_name="products")
    op.drop_index("ix_products_visible", table_name="products")

    op.drop_index("ix_cart_user", table_name="cart")
    op.drop_constraint("uq_cart_user_product", "cart", type_="unique")

    op.drop_index("ix_order_products_order", table_name="order_products")
    op.drop_column("order_products", "line_total")
    op.drop_column("order_products", "currency")
    op.drop_column("order_products", "unit_price")

    op.drop_index("ix_orders_user_date", table_name="orders")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_column("orders", "shipping_country_code")
    op.drop_column("orders", "shipping_postal_code")
    op.drop_column("orders", "shipping_state")
    op.drop_column("orders", "shipping_city")
    op.drop_column("orders", "shipping_address_line2")
    op.drop_column("orders", "shipping_address_line1")
    op.drop_column("orders", "currency")
    op.drop_column("orders", "order_number")
