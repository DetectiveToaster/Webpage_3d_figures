from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey, Table, DateTime, LargeBinary
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

# Association Table for Many-to-Many relationship between Products and Categories
product_categories = Table(
    'product_categories',
    Base.metadata,
    Column('product_id', Integer, ForeignKey('products.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('categories.id'), primary_key=True)
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
    cart = relationship("Cart", back_populates="user")


class Product(Base):
    """Generic product information shared across all product types."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    product_type = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    discount = Column(Numeric(10, 2), nullable=True)
    discounted_price = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    model3d = relationship("Model3D", back_populates="product", uselist=False)
    categories = relationship("Category", secondary=product_categories, back_populates="products")

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    products = relationship("Product", secondary=product_categories, back_populates="categories")

class Model3D(Base):
    """Specific information for 3D model products."""

    __tablename__ = "three_d_models"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True)
    height = Column(Numeric(10, 2), nullable=False)
    length = Column(Numeric(10, 2), nullable=False)
    width = Column(Numeric(10, 2), nullable=False)

    product = relationship("Product", back_populates="model3d")
    media = relationship("Model3DMedia", back_populates="model3d")


class Model3DMedia(Base):
    __tablename__ = "model3d_media"
    id = Column(Integer, primary_key=True)
    model3d_id = Column(Integer, ForeignKey("three_d_models.id"), nullable=False)
    media_type = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)

    model3d = relationship("Model3D", back_populates="media")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    total_cost = Column(Numeric(10, 2), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False)
    paypal_order_id = Column(String, nullable=True)
    
    # Fields for guest users
    guest_email = Column(String, nullable=True)
    guest_address = Column(String, nullable=True)

    user = relationship("User", back_populates="orders")
    products = relationship("OrderProduct", back_populates="order")

class OrderProduct(Base):
    __tablename__ = "order_products"

    order_id = Column(Integer, ForeignKey('orders.id'), primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), primary_key=True)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="products")
    product = relationship("Product")

class Cart(Base):
    __tablename__ = "cart"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cart")
    product = relationship("Product")
