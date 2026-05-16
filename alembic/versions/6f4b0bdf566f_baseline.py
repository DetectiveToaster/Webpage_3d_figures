"""baseline

Revision ID: 6f4b0bdf566f
Revises: 
Create Date: 2025-09-16 00:17:49.901015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f4b0bdf566f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount", sa.Numeric(10, 2), nullable=True),
        sa.Column("discounted_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_products_id", "products", ["id"])
    op.create_index("ix_products_type", "products", ["type"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_categories_id", "categories", ["id"])

    op.create_table(
        "product_categories",
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "three_d_models",
        sa.Column("id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("height", sa.Numeric(10, 2), nullable=False),
        sa.Column("length", sa.Numeric(10, 2), nullable=False),
        sa.Column("width", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_three_d_models_id", "three_d_models", ["id"])

    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("series", sa.String(), nullable=True),
        sa.Column("rarity", sa.String(), nullable=True),
        sa.Column("condition", sa.String(), nullable=True),
    )
    op.create_index("ix_cards_id", "cards", ["id"])

    op.create_table(
        "manuals",
        sa.Column("id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("format", sa.String(), nullable=True),
    )
    op.create_index("ix_manuals_id", "manuals", ["id"])

    op.create_table(
        "product_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_product_media_product_id", "product_media", ["product_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("paypal_order_id", sa.String(), nullable=True),
        sa.Column("guest_email", sa.String(), nullable=True),
        sa.Column("guest_address", sa.String(), nullable=True),
    )
    op.create_index("ix_orders_id", "orders", ["id"])

    op.create_table(
        "order_products",
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), primary_key=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
    )

    op.create_table(
        "cart",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_cart_id", "cart", ["id"])

    op.add_column('products', sa.Column('is_visible', sa.Boolean(), nullable=False))
    op.add_column('products', sa.Column('view_count', sa.Integer(), nullable=False))
    op.add_column('products', sa.Column('sold_count', sa.Integer(), nullable=False))
    op.add_column('products', sa.Column('last_viewed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'last_viewed_at')
    op.drop_column('products', 'sold_count')
    op.drop_column('products', 'view_count')
    op.drop_column('products', 'is_visible')
    op.drop_index("ix_cart_id", table_name="cart")
    op.drop_table("cart")
    op.drop_table("order_products")
    op.drop_index("ix_orders_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_product_media_product_id", table_name="product_media")
    op.drop_table("product_media")
    op.drop_index("ix_manuals_id", table_name="manuals")
    op.drop_table("manuals")
    op.drop_index("ix_cards_id", table_name="cards")
    op.drop_table("cards")
    op.drop_index("ix_three_d_models_id", table_name="three_d_models")
    op.drop_table("three_d_models")
    op.drop_table("product_categories")
    op.drop_index("ix_categories_id", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_products_type", table_name="products")
    op.drop_index("ix_products_id", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
