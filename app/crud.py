from sqlalchemy.orm import Session, selectinload
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from datetime import datetime
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
    
    # Add products to the order and update sold counters
    for product in order.products:
        db_order_product = models.OrderProduct(order_id=db_order.id, product_id=product.product_id, quantity=product.quantity)
        db.add(db_order_product)
        # Update sold_count
        db_product = db.query(models.Product).filter(models.Product.id == product.product_id).first()
        if db_product:
            db_product.sold_count = (db_product.sold_count or 0) + product.quantity
    db.commit()
    
    return db_order

"""Product and media CRUD helpers."""

# Product CRUD
def _compute_discounted_price(price: Decimal, discount_amount: Optional[Decimal]) -> Optional[Decimal]:
    if discount_amount is None:
        return None
    discounted = price - discount_amount
    if discounted < Decimal("0"):
        discounted = Decimal("0")
    return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def create_product(db: Session, product: schemas.ProductBase):
    # Creates a simple base product (no subtype specifics)
    data = product.dict(by_alias=False)
    # Ensure discounted_price is computed if discount provided but discounted_price missing
    if data.get("discount") is not None and data.get("discounted_price") is None:
        price = Decimal(str(data["price"]))
        discount = Decimal(str(data["discount"]))
        data["discounted_price"] = _compute_discounted_price(price, discount)
    db_product = models.Product(**data)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def get_product(db: Session, product_id: int):
    return (
        db.query(models.Product)
        .options(
            selectinload(models.Product.media),
            selectinload(models.Product.categories),
        )
        .filter(models.Product.id == product_id)
        .first()
    )

def get_products(db: Session, skip: int = 0, limit: int = 10):
    return (
        db.query(models.Product)
        .options(
            selectinload(models.Product.categories),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_visible_products(db: Session, skip: int = 0, limit: int = 10):
    return (
        db.query(models.Product)
        .options(
            selectinload(models.Product.categories),
        )
        .filter(models.Product.is_visible == True)
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_product(db: Session, product_id: int, product: schemas.ProductBase):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        for key, value in product.dict(by_alias=False).items():
            setattr(db_product, key, value)
        # recompute discounted_price if necessary
        if db_product.discount is not None and db_product.discounted_price is None:
            db_product.discounted_price = _compute_discounted_price(Decimal(str(db_product.price)), Decimal(str(db_product.discount)))
        db.commit()
        db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product

def create_product_3d(db: Session, product: schemas.Product3DCreate):
    # Instantiate the subclass directly; SQLAlchemy inserts parent + child
    db_obj = models.ThreeDModel(
        name=product.name,
        type=product.type,
        quantity=product.quantity,
        price=product.price,
        discount=product.discount,
        discounted_price=product.discounted_price if product.discounted_price is not None and product.discount is not None else (
            _compute_discounted_price(Decimal(str(product.price)), Decimal(str(product.discount))) if product.discount is not None else None
        ),
        height=product.height,
        length=product.length,
        width=product.width,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def create_card(db: Session, product: schemas.CardCreate):
    db_obj = models.Card(
        name=product.name,
        type=product.type,
        quantity=product.quantity,
        price=product.price,
        discount=product.discount,
        discounted_price=product.discounted_price if product.discounted_price is not None and product.discount is not None else (
            _compute_discounted_price(Decimal(str(product.price)), Decimal(str(product.discount))) if product.discount is not None else None
        ),
        series=product.series,
        rarity=product.rarity,
        condition=product.condition,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def create_manual(db: Session, product: schemas.ManualCreate):
    db_obj = models.Manual(
        name=product.name,
        type=product.type,
        quantity=product.quantity,
        price=product.price,
        discount=product.discount,
        discounted_price=product.discounted_price if product.discounted_price is not None and product.discount is not None else (
            _compute_discounted_price(Decimal(str(product.price)), Decimal(str(product.discount))) if product.discount is not None else None
        ),
        page_count=product.page_count,
        language=product.language,
        format=product.format,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def create_product_media(db: Session, media: schemas.ProductMediaCreate):
    db_media = models.ProductMedia(**media.dict())
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media

def get_media_for_product(db: Session, product_id: int):
    return db.query(models.ProductMedia).filter(models.ProductMedia.product_id == product_id).all()

def get_product_media_by_id(db: Session, media_id: int):
    return db.query(models.ProductMedia).filter(models.ProductMedia.id == media_id).first()

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
    return (
        db.query(models.Category)
        .options(selectinload(models.Category.products))
        .offset(skip)
        .limit(limit)
        .all()
    )

# Order CRUD
def create_order(db: Session, order: schemas.OrderBase):
    db_order = models.Order(**order.dict())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

def get_orders(db: Session, skip: int = 0, limit: int = 10):
    return db.query(models.Order).offset(skip).limit(limit).all()

def get_order(db: Session, order_id: int):
    return db.query(models.Order).filter(models.Order.id == order_id).first()

def update_order_status(db: Session, order_id: int, status: str):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order:
        order.status = status
        db.commit()
        db.refresh(order)
    return order

def set_paypal_order_id(db: Session, order_id: int, paypal_order_id: str):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order:
        order.paypal_order_id = paypal_order_id
        db.commit()
        db.refresh(order)
    return order

def get_order_by_paypal_id(db: Session, paypal_order_id: str):
    return db.query(models.Order).filter(models.Order.paypal_order_id == paypal_order_id).first()

# Cart CRUD
def add_to_cart(db: Session, cart: schemas.CartBase):
    db_cart = models.Cart(**cart.dict())
    db.add(db_cart)
    db.commit()
    db.refresh(db_cart)
    return db_cart

def get_cart_items(db: Session, user_id: int):
    return db.query(models.Cart).filter(models.Cart.user_id == user_id).all()

def update_cart_item(db: Session, cart_id: int, quantity: int):
    cart_item = db.query(models.Cart).filter(models.Cart.id == cart_id).first()
    if cart_item:
        cart_item.quantity = quantity
        db.commit()
        db.refresh(cart_item)
    return cart_item

def delete_cart_item(db: Session, cart_id: int):
    cart_item = db.query(models.Cart).filter(models.Cart.id == cart_id).first()
    if cart_item:
        db.delete(cart_item)
        db.commit()
    return cart_item


# --- View tracking and highlighting ---

def increment_product_view(db: Session, product_id: int):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        return None
    db_product.view_count = (db_product.view_count or 0) + 1
    db_product.last_viewed_at = datetime.utcnow()
    db.commit()
    db.refresh(db_product)
    return db_product


def get_highlighted_products(db: Session, limit: int = 10):
    # Fetch visible, in-stock products
    candidates = (
        db.query(models.Product)
        .options(selectinload(models.Product.categories))
        .filter(models.Product.is_visible == True)
        .filter(models.Product.quantity > 0)
        .all()
    )

    def score(p: models.Product) -> float:
        import math
        views = int(p.view_count or 0)
        sold = int(p.sold_count or 0)
        price = Decimal(str(p.price)) if p.price is not None else Decimal("0")
        discount_amt = Decimal(str(p.discount)) if p.discount is not None else Decimal("0")
        discount_ratio = float((discount_amt / price).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)) if price > 0 else 0.0
        discount_ratio = max(0.0, min(discount_ratio, 0.8))
        # Log-scaled signals
        v = math.log1p(views)
        s = math.log1p(sold)
        # Interest gap: high views but low sales
        gap = v * (1.0 - min(s / v if v > 0 else 0.0, 1.0))
        # Recency boost based on age
        days = 0.0
        if p.created_at:
            age = (datetime.utcnow() - p.created_at).days
            days = float(age)
        recency = math.exp(-(days / 45.0))
        # Weighted sum
        return 0.6 * s + 0.4 * v + 0.35 * gap + 0.3 * discount_ratio + 0.4 * recency

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[: max(0, int(limit))]


# --- Pricing and visibility management ---

def set_product_visibility(db: Session, product_id: int, is_visible: bool):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        return None
    db_product.is_visible = bool(is_visible)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_product_price(db: Session, product_id: int, price: float):
    if price < 0:
        raise ValueError("Price cannot be negative")
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        return None
    db_product.price = Decimal(str(price))
    # Recompute discounted_price if discount exists
    if db_product.discount is not None:
        db_product.discounted_price = _compute_discounted_price(Decimal(str(db_product.price)), Decimal(str(db_product.discount)))
    db.commit()
    db.refresh(db_product)
    return db_product


def apply_product_discount(db: Session, product_id: int, mode: str, value: float):
    """Apply discount either as percentage (0-100) or absolute amount.

    Stores the absolute discount in `discount` and updates `discounted_price`.
    """
    mode_l = (mode or "").lower()
    if mode_l not in ("percent", "amount"):
        raise ValueError("mode must be 'percent' or 'amount'")
    if value < 0:
        raise ValueError("Discount value cannot be negative")

    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        return None

    price = Decimal(str(db_product.price))
    if mode_l == "percent":
        if value > 100:
            raise ValueError("Percentage cannot exceed 100")
        discount_amount = (price * Decimal(str(value)) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        discount_amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if discount_amount > price:
            discount_amount = price

    db_product.discount = discount_amount
    db_product.discounted_price = _compute_discounted_price(price, discount_amount)
    db.commit()
    db.refresh(db_product)
    return db_product
