from sqlalchemy.orm import Session, selectinload, with_loader_criteria
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from datetime import datetime
import uuid
import os
from . import models, schemas
from .security import hash_password

ORDER_STATUS_VALUES = {
    "AWAITING_PAYMENT",
    "PAYMENT_RECEIVED",
    "IN_PRODUCTION",
    "READY",
    "SHIPPED",
    "COMPLETED",
    "CANCELLED",
    "EXPIRED",
}
PAYMENT_STATUS_VALUES = {"PENDING", "PAID", "FAILED", "REFUNDED"}
CANCELLED_STATUSES = {"CANCELLED", "EXPIRED"}
PAID_ORDER_STATUSES = {"PAYMENT_RECEIVED", "IN_PRODUCTION", "READY", "SHIPPED", "COMPLETED"}

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

def _order_number(seed: Optional[str] = None) -> str:
    return seed or uuid.uuid4().hex[:12].upper()


def _effective_product_price(product: models.Product) -> Decimal:
    value = product.discounted_price if product.discounted_price is not None else product.price
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_env(name: str, default: str) -> Decimal:
    try:
        return Decimal(os.getenv(name, default))
    except Exception:
        return Decimal(default)


def _build_order_products(
    db: Session,
    products: list[schemas.OrderLineCreate],
    currency: str,
    reserve_inventory: bool = False,
) -> tuple[list[models.OrderProduct], Decimal, int, int]:
    if not products:
        raise ValueError("Order must include at least one product")

    line_items: list[models.OrderProduct] = []
    total = Decimal("0.00")
    item_count = 0
    weight_grams = 0
    for item in products:
        db_product = (
            db.query(models.Product)
            .filter(models.Product.id == item.product_id)
            .filter(models.Product.is_visible == True)
            .filter(models.Product.status == "published")
            .first()
        )
        if not db_product:
            raise ValueError(f"Product {item.product_id} is not available")
        if item.quantity > db_product.quantity:
            raise ValueError(f"Product {item.product_id} does not have enough inventory")

        unit_price = _effective_product_price(db_product)
        line_total = _quantize(unit_price * Decimal(str(item.quantity)))
        total += line_total
        item_count += item.quantity
        if db_product.weight_grams:
            weight_grams += int(db_product.weight_grams) * item.quantity
        if reserve_inventory:
            db_product.quantity -= item.quantity
        line_items.append(
            models.OrderProduct(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=unit_price,
                currency=currency,
                line_total=line_total,
            )
        )
    return line_items, _quantize(total), item_count, weight_grams


def _matching_shipping_rule(db: Session, country_code: Optional[str], postal_code: Optional[str], currency: str):
    if not country_code:
        return None
    country_code = country_code.upper()
    query = (
        db.query(models.ShippingRateRule)
        .filter(models.ShippingRateRule.is_active == True)
        .filter(models.ShippingRateRule.country_code == country_code)
        .filter(models.ShippingRateRule.currency == currency)
    )
    candidates = query.all()
    exact_matches = [
        rule for rule in candidates
        if rule.postal_prefix and postal_code and postal_code.startswith(rule.postal_prefix)
    ]
    if exact_matches:
        return sorted(exact_matches, key=lambda r: len(r.postal_prefix or ""), reverse=True)[0]
    return next((rule for rule in candidates if not rule.postal_prefix), None)


def estimate_shipping_cost(
    db: Session,
    country_code: Optional[str],
    postal_code: Optional[str],
    subtotal: Decimal,
    item_count: int,
    weight_grams: int,
    currency: str,
) -> tuple[Decimal, Optional[int]]:
    rule = _matching_shipping_rule(db, country_code, postal_code, currency)
    if rule:
        if rule.free_shipping_min_subtotal is not None and subtotal >= Decimal(str(rule.free_shipping_min_subtotal)):
            return Decimal("0.00"), rule.estimated_delivery_days
        weight_kg = Decimal(str(weight_grams)) / Decimal("1000")
        cost = (
            Decimal(str(rule.base_cost))
            + Decimal(str(rule.per_item_cost)) * Decimal(str(item_count))
            + Decimal(str(rule.per_kg_cost)) * weight_kg
        )
        return _quantize(cost), rule.estimated_delivery_days

    free_min = _decimal_env("MANUAL_SHIPPING_FREE_MIN_SUBTOTAL", "0")
    if free_min > 0 and subtotal >= free_min:
        return Decimal("0.00"), None
    default_cost = _decimal_env("MANUAL_SHIPPING_DEFAULT_COST", "5.00")
    per_item = _decimal_env("MANUAL_SHIPPING_PER_ITEM_COST", "0.00")
    per_kg = _decimal_env("MANUAL_SHIPPING_PER_KG_COST", "0.00")
    weight_kg = Decimal(str(weight_grams)) / Decimal("1000")
    return _quantize(default_cost + per_item * Decimal(str(item_count)) + per_kg * weight_kg), None


def estimate_checkout(db: Session, checkout: schemas.CheckoutBase) -> tuple[list[models.OrderProduct], Decimal, Decimal, Decimal, Optional[int]]:
    line_items, subtotal, item_count, weight_grams = _build_order_products(db, checkout.products, checkout.currency)
    shipping_cost, estimated_days = estimate_shipping_cost(
        db,
        checkout.shipping_country_code,
        checkout.shipping_postal_code,
        subtotal,
        item_count,
        weight_grams,
        checkout.currency,
    )
    return line_items, subtotal, shipping_cost, _quantize(subtotal + shipping_cost), estimated_days


def _payment_instructions(method: str, order_number: str, total_cost: Decimal, currency: str) -> str:
    if method == "bizum":
        phone = os.getenv("BIZUM_PHONE", "the configured Bizum phone")
        return f"Send {total_cost} {currency} by Bizum to {phone}. Use order number {order_number} as the payment reference."
    if method == "bank_transfer":
        iban = os.getenv("BANK_TRANSFER_IBAN", "the configured bank account")
        beneficiary = os.getenv("BANK_TRANSFER_BENEFICIARY", "the store owner")
        return f"Transfer {total_cost} {currency} to {iban} ({beneficiary}). Use order number {order_number} as the payment reference."
    return os.getenv(
        "MANUAL_PAYMENT_INSTRUCTIONS",
        f"Contact the store team to confirm payment. Use order number {order_number} as the reference.",
    )


def _attach_order_products(order: models.Order, line_items: list[models.OrderProduct]) -> None:
    for line_item in line_items:
        order.products.append(line_item)


def _mark_order_items_sold(order: models.Order) -> None:
    for line_item in order.products:
        if not line_item.product:
            continue
        line_item.product.sold_count = (line_item.product.sold_count or 0) + line_item.quantity


def _unmark_order_items_sold(order: models.Order) -> None:
    for line_item in order.products:
        if not line_item.product:
            continue
        line_item.product.sold_count = max(0, (line_item.product.sold_count or 0) - line_item.quantity)


def _release_reserved_inventory(order: models.Order) -> None:
    for line_item in order.products:
        if line_item.product:
            line_item.product.quantity += line_item.quantity


def create_guest_order(db: Session, order: schemas.GuestOrderBase):
    line_items, subtotal, item_count, weight_grams = _build_order_products(db, order.products, order.currency, reserve_inventory=True)
    shipping_cost, _ = estimate_shipping_cost(
        db,
        order.shipping_country_code,
        order.shipping_postal_code,
        subtotal,
        item_count,
        weight_grams,
        order.currency,
    )
    total_cost = _quantize(subtotal + shipping_cost)
    order_number = _order_number()
    db_order = models.Order(
        guest_email=order.guest_email,
        guest_address=order.guest_address,
        phone=order.phone,
        customer_notes=order.customer_notes,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total_cost=total_cost,
        currency=order.currency,
        status="AWAITING_PAYMENT",
        payment_method=order.payment_method,
        payment_status="PENDING",
        payment_reference=order_number,
        payment_instructions=_payment_instructions(order.payment_method, order_number, total_cost, order.currency),
        order_number=order_number,
        shipping_address_line1=order.shipping_address_line1,
        shipping_address_line2=order.shipping_address_line2,
        shipping_city=order.shipping_city,
        shipping_state=order.shipping_state,
        shipping_postal_code=order.shipping_postal_code,
        shipping_country_code=order.shipping_country_code,
    )
    _attach_order_products(db_order, line_items)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

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
    data = product.model_dump(by_alias=False)
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
        .filter(models.Product.status == "published")
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_product(db: Session, product_id: int, product: schemas.ProductBase):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product:
        for key, value in product.model_dump(by_alias=False).items():
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
        is_visible=product.is_visible,
        production_type=product.production_type,
        material=product.material,
        color=product.color,
        scale=product.scale,
        estimated_production_days=product.estimated_production_days,
        requires_manual_review=product.requires_manual_review,
        weight_grams=product.weight_grams,
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
        is_visible=product.is_visible,
        production_type=product.production_type,
        material=product.material,
        color=product.color,
        scale=product.scale,
        estimated_production_days=product.estimated_production_days,
        requires_manual_review=product.requires_manual_review,
        weight_grams=product.weight_grams,
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
        is_visible=product.is_visible,
        production_type=product.production_type,
        material=product.material,
        color=product.color,
        scale=product.scale,
        estimated_production_days=product.estimated_production_days,
        requires_manual_review=product.requires_manual_review,
        weight_grams=product.weight_grams,
        page_count=product.page_count,
        language=product.language,
        format=product.format,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def create_product_media(db: Session, media: schemas.ProductMediaCreate):
    db_media = models.ProductMedia(**media.model_dump())
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

# Upload sessions
def create_upload_session(db: Session) -> models.UploadSession:
    session = models.UploadSession()
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def add_file_to_session(db: Session, session_id: int, filename: str, content_type: str, role: Optional[str], sort_order: int, data: bytes):
    upload = db.query(models.UploadSession).filter(models.UploadSession.id == session_id).first()
    if not upload:
        return None
    file_rec = models.UploadFile(
        session_id=session_id,
        filename=filename,
        content_type=content_type,
        role=role,
        sort_order=sort_order,
        data=data,
    )
    db.add(file_rec)
    db.commit()
    db.refresh(file_rec)
    return file_rec


def list_session_files(db: Session, session_id: int):
    return db.query(models.UploadFile).filter(models.UploadFile.session_id == session_id).order_by(models.UploadFile.sort_order, models.UploadFile.id).all()


def delete_upload_session(db: Session, session_id: int):
    session = db.query(models.UploadSession).filter(models.UploadSession.id == session_id).first()
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True


def commit_upload_session(db: Session, session_id: int, items: list[schemas.UploadCommitItem]):
    files_by_id = {
        f.id: f for f in db.query(models.UploadFile).filter(models.UploadFile.session_id == session_id).all()
    }
    if not files_by_id:
        return []
    created_media = []
    for item in items:
        f = files_by_id.get(item.file_id)
        if not f:
            continue
        media = models.ProductMedia(
            product_id=item.product_id,
            kind=item.kind,
            filename=f.filename,
            content_type=f.content_type,
            role=item.role or f.role,
            sort_order=item.sort_order if item.sort_order is not None else f.sort_order,
            data=f.data,
        )
        db.add(media)
        created_media.append(media)
    # Remove session and files after commit
    delete_upload_session(db, session_id)
    db.commit()
    for media in created_media:
        db.refresh(media)
    return created_media

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
        .options(
            selectinload(models.Category.products),
            with_loader_criteria(
                models.Product,
                (models.Product.is_visible == True) & (models.Product.status == "published"),
                include_aliases=True,
            ),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )

# Order CRUD
def create_order_for_user(db: Session, user_id: int, order: schemas.OrderCreate):
    line_items, subtotal, item_count, weight_grams = _build_order_products(db, order.products, order.currency, reserve_inventory=True)
    shipping_cost, _ = estimate_shipping_cost(
        db,
        order.shipping_country_code,
        order.shipping_postal_code,
        subtotal,
        item_count,
        weight_grams,
        order.currency,
    )
    total_cost = _quantize(subtotal + shipping_cost)
    order_number = _order_number()
    db_order = models.Order(
        user_id=user_id,
        phone=order.phone,
        customer_notes=order.customer_notes,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total_cost=total_cost,
        currency=order.currency,
        status="AWAITING_PAYMENT",
        payment_method=order.payment_method,
        payment_status="PENDING",
        payment_reference=order_number,
        payment_instructions=_payment_instructions(order.payment_method, order_number, total_cost, order.currency),
        order_number=order_number,
        shipping_address_line1=order.shipping_address_line1,
        shipping_address_line2=order.shipping_address_line2,
        shipping_city=order.shipping_city,
        shipping_state=order.shipping_state,
        shipping_postal_code=order.shipping_postal_code,
        shipping_country_code=order.shipping_country_code,
    )
    _attach_order_products(db_order, line_items)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

def get_orders(db: Session, skip: int = 0, limit: int = 10, status: Optional[str] = None, payment_status: Optional[str] = None):
    query = db.query(models.Order)
    if status:
        query = query.filter(models.Order.status == status)
    if payment_status:
        query = query.filter(models.Order.payment_status == payment_status)
    return query.order_by(models.Order.date.desc()).offset(skip).limit(limit).all()

def get_orders_for_user(db: Session, user_id: int, skip: int = 0, limit: int = 10):
    return db.query(models.Order).filter(models.Order.user_id == user_id).offset(skip).limit(limit).all()

def get_order(db: Session, order_id: int):
    return db.query(models.Order).filter(models.Order.id == order_id).first()

def get_order_by_number(db: Session, order_number: str):
    return db.query(models.Order).filter(models.Order.order_number == order_number).first()

def get_order_for_user(db: Session, order_id: int, user_id: int):
    return db.query(models.Order).filter(models.Order.id == order_id, models.Order.user_id == user_id).first()

def update_order_status(db: Session, order_id: int, status: str):
    status = status.upper()
    if status not in ORDER_STATUS_VALUES:
        raise ValueError("Invalid order status")
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order:
        old_status = order.status
        if old_status in CANCELLED_STATUSES and status not in CANCELLED_STATUSES:
            raise ValueError("Cancelled or expired orders cannot be reopened")
        order.status = status
        if status in PAID_ORDER_STATUSES and order.payment_status != "PAID":
            order.payment_status = "PAID"
            order.paid_at = datetime.utcnow()
            _mark_order_items_sold(order)
        if status in CANCELLED_STATUSES and old_status not in CANCELLED_STATUSES:
            _release_reserved_inventory(order)
            if order.payment_status == "PAID":
                _unmark_order_items_sold(order)
        if status == "SHIPPED" and not order.shipped_at:
            order.shipped_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
    return order

def update_order_admin(db: Session, order_id: int, payload: schemas.OrderAdminUpdate):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return None
    old_status = order.status
    old_payment_status = order.payment_status

    if payload.status is not None:
        status = payload.status.upper()
        if status not in ORDER_STATUS_VALUES:
            raise ValueError("Invalid order status")
        if old_status in CANCELLED_STATUSES and status not in CANCELLED_STATUSES:
            raise ValueError("Cancelled or expired orders cannot be reopened")
        order.status = status
    if payload.payment_status is not None:
        payment_status = payload.payment_status.upper()
        if payment_status not in PAYMENT_STATUS_VALUES:
            raise ValueError("Invalid payment status")
        if order.status in CANCELLED_STATUSES and payment_status == "PAID":
            raise ValueError("Cancelled or expired orders cannot be marked as paid")
        order.payment_status = payment_status
    if payload.payment_reference is not None:
        order.payment_reference = payload.payment_reference
    if payload.admin_notes is not None:
        order.admin_notes = payload.admin_notes
    if payload.tracking_number is not None:
        order.tracking_number = payload.tracking_number
    if payload.shipping_carrier is not None:
        order.shipping_carrier = payload.shipping_carrier

    if order.payment_status == "PAID" and old_payment_status != "PAID":
        order.paid_at = datetime.utcnow()
        if order.status == "AWAITING_PAYMENT":
            order.status = "PAYMENT_RECEIVED"
        _mark_order_items_sold(order)
    if order.status in PAID_ORDER_STATUSES and order.payment_status != "PAID":
        order.payment_status = "PAID"
        order.paid_at = datetime.utcnow()
        _mark_order_items_sold(order)
    if order.status in CANCELLED_STATUSES and old_status not in CANCELLED_STATUSES:
        _release_reserved_inventory(order)
        if old_payment_status == "PAID" or order.payment_status == "PAID":
            _unmark_order_items_sold(order)
    if order.status == "SHIPPED" and not order.shipped_at:
        order.shipped_at = datetime.utcnow()

    db.commit()
    db.refresh(order)
    return order

def add_order_attachment(db: Session, order_id: int, filename: str, content_type: str, role: Optional[str], data: bytes):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return None
    attachment = models.OrderAttachment(
        order_id=order_id,
        filename=filename,
        content_type=content_type,
        role=role,
        data=data,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment

def create_shipping_rate_rule(db: Session, rule: schemas.ShippingRateRuleCreate):
    db_rule = models.ShippingRateRule(**rule.model_dump())
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def get_shipping_rate_rules(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.ShippingRateRule).order_by(models.ShippingRateRule.country_code, models.ShippingRateRule.postal_prefix).offset(skip).limit(limit).all()

def update_shipping_rate_rule(db: Session, rule_id: int, payload: schemas.ShippingRateRuleUpdate):
    db_rule = db.query(models.ShippingRateRule).filter(models.ShippingRateRule.id == rule_id).first()
    if not db_rule:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_rule, key, value)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def delete_shipping_rate_rule(db: Session, rule_id: int):
    db_rule = db.query(models.ShippingRateRule).filter(models.ShippingRateRule.id == rule_id).first()
    if not db_rule:
        return None
    db.delete(db_rule)
    db.commit()
    return db_rule

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
def add_to_cart(db: Session, user_id: int, cart: schemas.CartBase):
    db_product = (
        db.query(models.Product)
        .filter(models.Product.id == cart.product_id)
        .filter(models.Product.is_visible == True)
        .filter(models.Product.status == "published")
        .first()
    )
    if not db_product:
        raise ValueError("Product is not available")
    if cart.quantity > db_product.quantity:
        raise ValueError("Not enough inventory")

    db_cart = (
        db.query(models.Cart)
        .filter(models.Cart.user_id == user_id, models.Cart.product_id == cart.product_id)
        .first()
    )
    if db_cart:
        db_cart.quantity = cart.quantity
    else:
        db_cart = models.Cart(user_id=user_id, product_id=cart.product_id, quantity=cart.quantity)
        db.add(db_cart)
    db.commit()
    db.refresh(db_cart)
    return db_cart

def get_cart_items(db: Session, user_id: int):
    return db.query(models.Cart).filter(models.Cart.user_id == user_id).all()

def update_cart_item(db: Session, user_id: int, cart_id: int, quantity: int):
    cart_item = db.query(models.Cart).filter(models.Cart.id == cart_id, models.Cart.user_id == user_id).first()
    if cart_item:
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")
        if quantity > cart_item.product.quantity:
            raise ValueError("Not enough inventory")
        cart_item.quantity = quantity
        db.commit()
        db.refresh(cart_item)
    return cart_item

def delete_cart_item(db: Session, user_id: int, cart_id: int):
    cart_item = db.query(models.Cart).filter(models.Cart.id == cart_id, models.Cart.user_id == user_id).first()
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
        .filter(models.Product.status == "published")
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
