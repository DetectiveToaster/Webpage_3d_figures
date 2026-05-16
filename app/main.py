# app/main.py

from fastapi import FastAPI, Depends, HTTPException, status, File, Form, UploadFile, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from urllib.parse import quote
from . import crud, models, schemas, auth, paypal, shipping
from .database import SessionLocal, engine
from .auth import authenticate_user, create_access_token, get_current_active_user, admin_required
import os
import warnings

# Initialize the database (guarded; prefer Alembic migrations in production)
if os.getenv("RUN_CREATE_ALL") == "true":
    models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def _cors_origins() -> List[str]:
    value = os.getenv("CORS_ORIGINS")
    if value:
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(150 * 1024 * 1024)))
ALLOWED_UPLOAD_TYPES_BY_EXTENSION = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".gif": {"image/gif"},
    ".glb": {"model/gltf-binary", "application/octet-stream"},
    ".gltf": {"model/gltf+json", "application/json", "application/octet-stream"},
    ".pdf": {"application/pdf"},
    ".stl": {"model/stl", "application/sla", "application/vnd.ms-pki.stl", "application/octet-stream"},
}
ALLOWED_UPLOAD_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "model/gltf-binary",
    "model/gltf+json",
    "application/pdf",
    "model/stl",
    "application/sla",
    "application/vnd.ms-pki.stl",
    "application/octet-stream",
}
STL_CONTENT_TYPES = ALLOWED_UPLOAD_TYPES_BY_EXTENSION[".stl"]


def normalise_upload_metadata(file: UploadFile) -> tuple[str, str]:
    filename = os.path.basename(file.filename or "")
    extension = os.path.splitext(filename)[1].lower()
    content_type = file.content_type or "application/octet-stream"
    allowed_types = ALLOWED_UPLOAD_TYPES_BY_EXTENSION.get(extension)
    if not filename or allowed_types is None:
        raise HTTPException(status_code=400, detail="File extension is not allowed")
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="File type does not match the file extension")
    if extension == ".stl" and content_type == "application/octet-stream":
        content_type = "model/stl"
    return filename, content_type


def read_limited_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large")
    return data


def paypal_configured() -> bool:
    return bool(os.getenv("ENABLE_PAYPAL") == "true" and os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_SECRET"))


def require_paypal_configured():
    if not paypal_configured():
        raise HTTPException(status_code=503, detail="Payment provider not configured")


@app.get("/health")
def health():
    return {"status": "ok"}

# Dependency to get DB session
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_admin_user():
    db = SessionLocal()
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    # Remove hardcoded testing values; rely on env
    # admin_email = "mail"
    # admin_password = "pass"

    if not admin_email or not admin_password:
        warnings.warn("Admin seed skipped: set ADMIN_EMAIL and ADMIN_PASSWORD to auto-create an admin user.")
        db.close()
        return

    if len(admin_password) > 72:
        warnings.warn("ADMIN_PASSWORD is longer than 72 characters; truncating for bcrypt compatibility.")
        admin_password = admin_password[:72]

    existing_user = db.query(models.User).filter(models.User.email == admin_email).first()
    if not existing_user:
        hashed_password = auth.hash_password(admin_password)
        admin_user = models.User(
            email=admin_email,
            password=hashed_password,
            is_admin=True
        )
        db.add(admin_user)
        try:
            db.commit()
            print(f"Admin user '{admin_email}' created.")
        except IntegrityError:
            db.rollback()
            print(f"Admin user '{admin_email}' already exists.")
    else:
        print(f"Admin user '{admin_email}' already exists.")
    db.close()

@app.on_event("startup")
def startup_event():
    create_admin_user()

# Endpoint to create a new user
@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db_session)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

# Endpoint to generate JWT token for authentication
@app.post("/token", response_model=schemas.Token)
def login_for_access_token(db: Session = Depends(get_db_session), form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# Secure endpoint to get current logged-in user
@app.get("/users/me/", response_model=schemas.UserProfile)
@app.get("/users/me", response_model=schemas.UserProfile)
def read_users_me(response: Response, current_user: models.User = Depends(get_current_active_user)):
    # Prevent caching of sensitive user info
    response.headers["Cache-Control"] = "no-store"
    return current_user

# Secure endpoint to create a new product (base type)
@app.post("/products/", response_model=schemas.Product)
def create_product(product: schemas.ProductBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_product(db=db, product=product)

"""
Public endpoints show only visible products by default. Admin endpoints allow
management of visibility and pricing/discounts and listing all.
"""

# Public endpoint to get a list of visible products
@app.get("/products/", response_model=List[schemas.Product])
def read_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session)):
    products = crud.get_visible_products(db, skip=skip, limit=limit)
    return products

@app.post("/shipping/quote", response_model=schemas.ShippingQuoteResponse)
def calculate_shipping_quote(payload: schemas.ShippingQuoteRequest, db: Session = Depends(get_db_session)):
    if os.getenv("ENABLE_CARRIER_SHIPPING") != "true":
        estimated = crud.estimate_shipping_cost(
            db,
            payload.destination.country_code,
            payload.destination.postal_code,
            Decimal("0.00"),
            1,
            int(payload.package.weight_kg * 1000),
            payload.currency,
        )
        return {
            "quotes": [
                schemas.ShippingQuote(
                    carrier="manual",
                    service="Manual estimate",
                    cost=float(estimated[0]),
                    currency=payload.currency,
                    estimated_delivery_days=estimated[1],
                    raw={"source": "manual_estimator"},
                )
            ],
            "errors": {},
        }
    quotes, errors = shipping.get_shipping_quotes(payload)
    if not quotes and errors:
        raise HTTPException(status_code=502, detail={"message": "No shipping rates available", "errors": errors})
    return {"quotes": quotes, "errors": errors}


@app.post("/shipping/estimate", response_model=schemas.ManualShippingEstimate)
def estimate_checkout_shipping(payload: schemas.ManualShippingEstimateRequest, db: Session = Depends(get_db_session)):
    try:
        _, subtotal, shipping_cost, total_cost, estimated_days = crud.estimate_checkout(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "subtotal": float(subtotal),
        "shipping_cost": float(shipping_cost),
        "total_cost": float(total_cost),
        "currency": payload.currency,
        "estimated_delivery_days": estimated_days,
    }

# Public: register a product view (call from product page render)
@app.post("/products/{product_id}/view", response_model=schemas.Product)
def register_product_view(product_id: int, db: Session = Depends(get_db_session)):
    product = crud.get_product(db, product_id)
    if product is None or not product.is_visible or product.status != "published":
        raise HTTPException(status_code=404, detail="Product not found")
    db_product = crud.increment_product_view(db, product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Secure endpoint to update a product by ID
@app.put("/products/{product_id}", response_model=schemas.Product)
def update_product(product_id: int, product: schemas.ProductBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    db_product = crud.update_product(db=db, product_id=product_id, product=product)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Secure endpoint to delete a product by ID
@app.delete("/products/{product_id}", response_model=schemas.Product)
def delete_product(product_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    db_product = crud.delete_product(db=db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Admin-only: list all products (including hidden)
@app.get("/products/all", response_model=List[schemas.Product])
def read_all_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.get_products(db, skip=skip, limit=limit)

# Admin-only: set product visibility
@app.patch("/products/{product_id}/visibility", response_model=schemas.Product)
def set_product_visibility(product_id: int, payload: schemas.ProductVisibilityUpdate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    db_product = crud.set_product_visibility(db, product_id, payload.is_visible)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Admin-only: update product price
@app.patch("/products/{product_id}/price", response_model=schemas.Product)
def update_product_price(product_id: int, payload: schemas.ProductPriceUpdate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    try:
        db_product = crud.update_product_price(db, product_id, payload.price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Admin-only: apply product discount (percent or amount)
@app.patch("/products/{product_id}/discount", response_model=schemas.Product)
def apply_product_discount(product_id: int, payload: schemas.ProductDiscountUpdate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    try:
        db_product = crud.apply_product_discount(db, product_id, payload.mode, payload.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Public: highlighted products for landing page
@app.get("/products/highlighted", response_model=List[schemas.Product])
def highlighted_products(limit: int = 12, db: Session = Depends(get_db_session)):
    return crud.get_highlighted_products(db, limit=limit)

# Public endpoint to get a single product by ID
@app.get("/products/{product_id}", response_model=schemas.Product)
def get_product(product_id: int, db: Session = Depends(get_db_session)):
    db_product = crud.get_product(db, product_id=product_id)
    if db_product is None or not db_product.is_visible or db_product.status != "published":
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

@app.post("/products/3d", response_model=schemas.Product)
def create_product_3d(product: schemas.Product3DCreate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_product_3d(db=db, product=product)

@app.post("/products/cards", response_model=schemas.Product)
def create_card(product: schemas.CardCreate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_card(db=db, product=product)

@app.post("/products/manuals", response_model=schemas.Product)
def create_manual(product: schemas.ManualCreate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_manual(db=db, product=product)

@app.post("/product_media/", response_model=schemas.ProductMedia)
def create_product_media(
    media: schemas.ProductMediaCreate,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    return crud.create_product_media(db=db, media=media)

@app.get("/product_media/product/{product_id}", response_model=List[schemas.ProductMedia])
def get_media_for_product(
    product_id: int,
    db: Session = Depends(get_db_session),
):
    db_product = crud.get_product(db, product_id=product_id)
    if db_product is None or not db_product.is_visible or db_product.status != "published":
        raise HTTPException(status_code=404, detail="Product not found")
    return crud.get_media_for_product(db=db, product_id=product_id)

@app.delete("/product_media/{media_id}", response_model=schemas.ProductMedia)
def delete_product_media(
    media_id: int,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    db_media = crud.delete_product_media(db=db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return db_media

@app.post("/product_media/upload/", response_model=schemas.ProductMedia)
def upload_product_media(
    product_id: int = Form(...),
    media_type: str = Form(...),  # "image" | "model" | "pdf"
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),  # Admin only
):
    filename, content_type = normalise_upload_metadata(file)
    db_product = crud.get_product(db, product_id)
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    file_bytes = read_limited_upload(file)
    db_media = models.ProductMedia(
        product_id=product_id,
        kind=media_type,
        filename=filename,
        content_type=content_type,
        data=file_bytes,
    )
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media

# --- Batch upload pipeline ---

@app.post("/admin/uploads", response_model=schemas.UploadSessionCreateResponse)
def create_upload_session_route(db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    session = crud.create_upload_session(db)
    return {"upload_id": session.id}


@app.get("/admin/uploads/{upload_id}/files", response_model=List[schemas.UploadFile])
def list_upload_files(upload_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    files = crud.list_session_files(db, upload_id)
    if files is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return files


@app.post("/admin/uploads/{upload_id}/files", response_model=schemas.UploadFile)
def add_file_to_upload(
    upload_id: int,
    role: str = Form(None),
    sort_order: int = Form(0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    filename, content_type = normalise_upload_metadata(file)
    data = read_limited_upload(file)
    rec = crud.add_file_to_session(
        db,
        session_id=upload_id,
        filename=filename,
        content_type=content_type,
        role=role,
        sort_order=sort_order or 0,
        data=data,
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return rec


@app.post("/admin/uploads/{upload_id}/commit", response_model=List[schemas.ProductMedia])
def commit_upload(
    upload_id: int,
    payload: schemas.UploadCommitRequest,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    created = crud.commit_upload_session(db, upload_id, payload.items)
    if created is None:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return created


@app.delete("/admin/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    ok = crud.delete_upload_session(db, upload_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return Response(status_code=204)

@app.get("/media/{media_id}")
def get_media_file(media_id: int, db: Session = Depends(get_db_session)):
    media = db.query(models.ProductMedia).filter(models.ProductMedia.id == media_id).first()
    if not media or not media.product or not media.product.is_visible or media.product.status != "published":
        raise HTTPException(status_code=404, detail="Media not found")
    return Response(
        content=media.data,
        media_type=media.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(media.filename)}",
            "X-Content-Type-Options": "nosniff",
        }
    )

# Secure endpoint to create a new category
@app.post("/categories/", response_model=schemas.Category)
def create_category(category: schemas.CategoryBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_category(db=db, category=category)

# Public endpoint to get a list of categories
@app.get("/categories/", response_model=List[schemas.Category])
def read_categories(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session)):
    categories = crud.get_categories(db, skip=skip, limit=limit)
    return categories

# Secure endpoint to create a new order for the current user
@app.post("/orders/", response_model=schemas.Order)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    try:
        return crud.create_order_for_user(db=db, user_id=current_user.id, order=order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Admin endpoint to get a list of all orders
@app.get("/orders/", response_model=List[schemas.Order])
def read_orders(
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    orders = crud.get_orders(db, skip=skip, limit=limit, status=status, payment_status=payment_status)
    return orders

@app.get("/orders/me", response_model=List[schemas.Order])
def read_my_orders(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.get_orders_for_user(db, user_id=current_user.id, skip=skip, limit=limit)

@app.get("/orders/{order_id}", response_model=schemas.Order)
def read_order(order_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    order = crud.get_order(db, order_id) if current_user.is_admin else crud.get_order_for_user(db, order_id, current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.post("/guest_orders/", response_model=schemas.Order)
def create_guest_order(order: schemas.GuestOrderBase, db: Session = Depends(get_db_session)):
    try:
        return crud.create_guest_order(db=db, order=order)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/guest_orders/{order_number}", response_model=schemas.Order)
def read_guest_order(order_number: str, email: str, db: Session = Depends(get_db_session)):
    order = crud.get_order_by_number(db, order_number)
    if not order or (order.guest_email or "").lower() != email.lower():
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/admin/orders/{order_id}", response_model=schemas.Order)
def read_admin_order(order_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/admin/orders/by-number/{order_number}", response_model=schemas.Order)
def read_admin_order_by_number(order_number: str, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    order = crud.get_order_by_number(db, order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.patch("/admin/orders/{order_id}", response_model=schemas.Order)
def update_admin_order(
    order_id: int,
    payload: schemas.OrderAdminUpdate,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    try:
        order = crud.update_order_admin(db, order_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.post("/admin/orders/{order_id}/mark-paid", response_model=schemas.Order)
def mark_order_paid(order_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    order = crud.update_order_admin(db, order_id, schemas.OrderAdminUpdate(payment_status="PAID"))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.post("/admin/orders/{order_id}/attachments", response_model=schemas.OrderAttachment)
def upload_order_attachment(
    order_id: int,
    role: str = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    filename, content_type = normalise_upload_metadata(file)
    attachment = crud.add_order_attachment(db, order_id, filename, content_type, role, read_limited_upload(file))
    if not attachment:
        raise HTTPException(status_code=404, detail="Order not found")
    return attachment


@app.post("/admin/shipping-rules", response_model=schemas.ShippingRateRule)
def create_shipping_rule(rule: schemas.ShippingRateRuleCreate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_shipping_rate_rule(db, rule)


@app.get("/admin/shipping-rules", response_model=List[schemas.ShippingRateRule])
def list_shipping_rules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.get_shipping_rate_rules(db, skip=skip, limit=limit)


@app.patch("/admin/shipping-rules/{rule_id}", response_model=schemas.ShippingRateRule)
def update_shipping_rule(rule_id: int, payload: schemas.ShippingRateRuleUpdate, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    rule = crud.update_shipping_rate_rule(db, rule_id, payload)
    if not rule:
        raise HTTPException(status_code=404, detail="Shipping rule not found")
    return rule


@app.delete("/admin/shipping-rules/{rule_id}", response_model=schemas.ShippingRateRule)
def delete_shipping_rule(rule_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    rule = crud.delete_shipping_rate_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Shipping rule not found")
    return rule

# PayPal integration endpoints

class CreatePayPalOrder(BaseModel):
    amount: float


@app.post("/paypal/create-order")
def paypal_create_order(payload: CreatePayPalOrder, current_user: models.User = Depends(admin_required)):
    """Admin-only utility for creating a PayPal order with an explicit amount."""
    require_paypal_configured()
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    return paypal.create_order(
        amount=payload.amount,
        return_url=os.getenv("PAYPAL_RETURN_URL", "https://example.com/success"),
        cancel_url=os.getenv("PAYPAL_CANCEL_URL", "https://example.com/cancel"),
    )


@app.post("/paypal/order/{order_id}")
def create_paypal_order(order_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    require_paypal_configured()
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not current_user.is_admin and order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    res = paypal.create_order(
        amount=float(order.total_cost),
        return_url=os.getenv("PAYPAL_RETURN_URL", "https://example.com/success"),
        cancel_url=os.getenv("PAYPAL_CANCEL_URL", "https://example.com/cancel"),
    )
    crud.set_paypal_order_id(db, order_id, res.get("id"))
    return res


@app.post("/paypal/capture-order/{paypal_order_id}")
def capture_paypal_order(paypal_order_id: str, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    """Capture a previously created PayPal order."""
    require_paypal_configured()
    order = crud.get_order_by_paypal_id(db, paypal_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not current_user.is_admin and order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    result = paypal.capture_order(paypal_order_id)
    crud.update_order_status(db, order.id, "COMPLETED")
    return result


@app.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(get_db_session)):
    require_paypal_configured()
    body = await request.json()
    if not paypal.verify_webhook(request.headers, body):
        raise HTTPException(status_code=400, detail="Invalid webhook")
    event_type = body.get("event_type")
    if event_type == "CHECKOUT.ORDER.APPROVED":
        order_id = body["resource"]["id"]
        order = crud.get_order_by_paypal_id(db, order_id)
        if order:
            crud.update_order_status(db, order.id, "PAYMENT_RECEIVED")
    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        related = body["resource"].get("supplementary_data", {}).get("related_ids", {})
        order_id = related.get("order_id")
        if order_id:
            order = crud.get_order_by_paypal_id(db, order_id)
            if order:
                crud.update_order_status(db, order.id, "COMPLETED")
    return {"status": "ok"}

# Secure endpoint to add an item to the cart
@app.post("/cart/", response_model=schemas.Cart)
def add_to_cart(cart: schemas.CartBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    try:
        return crud.add_to_cart(db=db, user_id=current_user.id, cart=cart)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Secure endpoint to view the cart of the current user
@app.get("/cart/", response_model=List[schemas.Cart])
def read_cart(db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.get_cart_items(db=db, user_id=current_user.id)

@app.put("/cart/{cart_id}", response_model=schemas.Cart)
def update_cart_item(cart_id: int, quantity: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    try:
        cart_item = crud.update_cart_item(db, current_user.id, cart_id, quantity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return cart_item

@app.delete("/cart/{cart_id}", response_model=schemas.Cart)
def delete_cart_item(cart_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    cart_item = crud.delete_cart_item(db, current_user.id, cart_id)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return cart_item
