"""Split product table and add 3D model tables

Revision ID: 7c2e9f3b7a9a
Revises: 336e981c18a7
Create Date: 2024-09-03 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7c2e9f3b7a9a'
down_revision: Union[str, None] = '336e981c18a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'three_d_models',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('height', sa.Numeric(10, 2), nullable=False),
        sa.Column('length', sa.Numeric(10, 2), nullable=False),
        sa.Column('width', sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'])
    )
    op.create_table(
        'model3d_media',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('model3d_id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['model3d_id'], ['three_d_models.id'])
    )
    op.add_column('products', sa.Column('product_type', sa.String(), nullable=False))
    op.add_column('products', sa.Column('price', sa.Numeric(10, 2), nullable=False))
    op.add_column('products', sa.Column('discount', sa.Numeric(10, 2), nullable=True))
    op.add_column('products', sa.Column('discounted_price', sa.Numeric(10, 2), nullable=True))
    op.drop_column('products', 'production_cost')
    op.drop_column('products', 'selling_cost')
    op.drop_column('products', 'height')
    op.drop_column('products', 'length')
    op.drop_column('products', 'depth')
    op.drop_table('product_media')


def downgrade() -> None:
    op.create_table(
        'product_media',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'])
    )
    op.add_column('products', sa.Column('depth', sa.Numeric(10, 2), nullable=False))
    op.add_column('products', sa.Column('length', sa.Numeric(10, 2), nullable=False))
    op.add_column('products', sa.Column('height', sa.Numeric(10, 2), nullable=False))
    op.add_column('products', sa.Column('selling_cost', sa.Numeric(10, 2), nullable=False))
    op.add_column('products', sa.Column('production_cost', sa.Numeric(10, 2), nullable=False))
    op.drop_column('products', 'discounted_price')
    op.drop_column('products', 'discount')
    op.drop_column('products', 'price')
    op.drop_column('products', 'product_type')
    op.drop_table('model3d_media')
    op.drop_table('three_d_models')
