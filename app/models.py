from sqlalchemy import Column, Integer, String, Boolean ,Numeric, ForeignKey, Table, DateTime, LargeBinary
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
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    production_cost = Column(Numeric(10, 2), nullable=False)
    selling_cost = Column(Numeric(10, 2), nullable=False)
    height = Column(Numeric(10, 2), nullable=False)
    length = Column(Numeric(10, 2), nullable=False)
    depth = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    media = relationship("ProductMedia", back_populates="product")
    categories = relationship("Category", secondary=product_categories, back_populates="products")

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    products = relationship("Product", secondary=product_categories, back_populates="categories")

class ProductMedia(Base):
    __tablename__ = "product_media"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    media_type = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)  
    data = Column(LargeBinary, nullable=False)     

    product = relationship("Product", back_populates="media")

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
