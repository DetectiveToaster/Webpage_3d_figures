from sqlalchemy.orm import Session
from . import models, schemas
from .security import hash_password

# User CRUD
def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = hash_password(user.password)
    db_user = models.User(email=user.email, password=hashed_password, address=user.address)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def get_users(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.User).offset(skip).limit(limit).all()

# app/crud.py

def create_guest_order(db: Session, order: schemas.GuestOrderBase):
    db_order = models.Order(
        guest_email=order.guest_email,
        guest_address=order.guest_address,
        total_cost=order.total_cost,
        status=order.status
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    # Add products to the order
    for product in order.products:
        db_order_product = models.OrderProduct(order_id=db_order.id, product_id=product.product_id, quantity=product.quantity)
        db.add(db_order_product)
    db.commit()
    
    return db_order

# Product CRUD
def create_product(db: Session, product: schemas.ProductBase):
    db_product = models.Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def get_product(db: Session, product_id: int):
    return db.query(models.Product).filter(models.Product.id == product_id).first()

def get_products(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.Product).offset(skip).limit(limit).all()

def update_product(db: Session, product_id: int, product: schemas.ProductBase):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        for key, value in product.dict().items():
            setattr(db_product, key, value)
        db.commit()
        db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product

# Create
def create_product_media(db: Session, media: schemas.ProductMediaCreate):
    db_media = models.ProductMedia(**media.dict())
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media

# Read - all media for a given product
def get_media_for_product(db: Session, product_id: int):
    return db.query(models.ProductMedia).filter(models.ProductMedia.product_id == product_id).all()

# Read - get by id
def get_product_media_by_id(db: Session, media_id: int):
    return db.query(models.ProductMedia).filter(models.ProductMedia.id == media_id).first()

# Delete
def delete_product_media(db: Session, media_id: int):
    db_media = db.query(models.ProductMedia).filter(models.ProductMedia.id == media_id).first()
    if db_media is None:
        return None
    db.delete(db_media)
    db.commit()
    return db_media

# Category CRUD
def create_category(db: Session, category: schemas.CategoryBase):
    db_category = models.Category(name=category.name)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def get_categories(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.Category).offset(skip).limit(limit).all()

# Order CRUD
def create_order(db: Session, order: schemas.OrderBase):
    db_order = models.Order(**order.dict())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

def get_orders(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.Order).offset(skip).limit(limit).all()

# Cart CRUD
def add_to_cart(db: Session, cart: schemas.CartBase):
    db_cart = models.Cart(**cart.dict())
    db.add(db_cart)
    db.commit()
    db.refresh(db_cart)
    return db_cart

def get_cart_items(db: Session, user_id: int):
    return db.query(models.Cart).filter(models.Cart.user_id == user_id).all()
