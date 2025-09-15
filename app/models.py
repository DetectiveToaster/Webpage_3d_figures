from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, Table, DateTime, LargeBinary
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

# Association Table for Many-to-Many relationship between Products and Categories
product_categories = Table(
    'product_categories',
    Base.metadata,
    Column('product_id', Integer, ForeignKey('products.id', ondelete="CASCADE"), primary_key=True),
    Column('category_id', Integer, ForeignKey('categories.id', ondelete="CASCADE"), primary_key=True)
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    address = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Add this relationship
    orders = relationship("Order", back_populates="user")
    cart = relationship("Cart", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Product(Base):
    """Base product with polymorphic subtypes (3D model, card, manual)."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    # Discriminator for SQLAlchemy polymorphism
    type = Column(String(50), nullable=False, index=True)

    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    discount = Column(Numeric(10, 2), nullable=True)
    discounted_price = Column(Numeric(10, 2), nullable=True)
    is_visible = Column(Boolean, nullable=False, default=True)
    view_count = Column(Integer, nullable=False, default=0)
    sold_count = Column(Integer, nullable=False, default=0)
    last_viewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def product_type(self):
        return self.type

    @product_type.setter
    def product_type(self, value):
        self.type = value

    # Relationships
    categories = relationship(
        "Category",
        secondary=product_categories,
        back_populates="products",
        lazy="selectin",
    )
    media = relationship(
        "ProductMedia",
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "base",
    }

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)

    products = relationship(
        "Product",
        secondary=product_categories,
        back_populates="categories",
        lazy="selectin",
    )

class ThreeDModel(Product):
    """Specific information for 3D model products (joined-table inheritance)."""

    __tablename__ = "three_d_models"

    # In joined-table inheritance, the PK is also a FK to products.id
    id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True, index=True)
    height = Column(Numeric(10, 2), nullable=False)
    length = Column(Numeric(10, 2), nullable=False)
    width = Column(Numeric(10, 2), nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "3d",
    }

class Card(Product):
    __tablename__ = "cards"

    id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True, index=True)
    series = Column(String, nullable=True)
    rarity = Column(String, nullable=True)
    condition = Column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "card",
    }

class Manual(Product):
    __tablename__ = "manuals"

    id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True, index=True)
    page_count = Column(Integer, nullable=True)
    language = Column(String, nullable=True)
    format = Column(String, nullable=True)  # e.g., "pdf", "epub"

    __mapper_args__ = {
        "polymorphic_identity": "manual",
    }

class ProductMedia(Base):
    __tablename__ = "product_media"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String, nullable=False)  # image | model | pdf | etc.
    role = Column(String, nullable=True)   # thumbnail | gallery | source | etc.
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)

    product = relationship("Product", back_populates="media")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True)
    total_cost = Column(Numeric(10, 2), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False)
    paypal_order_id = Column(String, nullable=True)
    
    # Fields for guest users
    guest_email = Column(String, nullable=True)
    guest_address = Column(String, nullable=True)

    user = relationship("User", back_populates="orders")
    products = relationship("OrderProduct", back_populates="order", cascade="all, delete-orphan", passive_deletes=True)

class OrderProduct(Base):
    __tablename__ = "order_products"

    order_id = Column(Integer, ForeignKey('orders.id', ondelete="CASCADE"), primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), primary_key=True)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="products")
    product = relationship("Product")

class Cart(Base):
    __tablename__ = "cart"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cart", passive_deletes=True)
    product = relationship("Product")
