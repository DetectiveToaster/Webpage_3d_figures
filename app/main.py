# app/main.py

from fastapi import FastAPI, Depends, HTTPException, status, File, Form, UploadFile, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from . import crud, models, schemas, auth, paypal
from .database import SessionLocal, engine
from .auth import authenticate_user, create_access_token, get_current_active_user, admin_required
import os

# Initialize the database
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # or ["*"] for all origins during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_admin_user():
    db = SessionLocal()
    admin_email = "admin@example.com"
    admin_password = "your_secure_password"

    existing_user = db.query(models.User).filter(models.User.email == admin_email).first()
    if not existing_user:
        hashed_password = auth.hash_password(admin_password)
        admin_user = models.User(
            email=admin_email,
            password=hashed_password,
            is_admin=True
        )
        db.add(admin_user)
        db.commit()
        print(f"Admin user '{admin_email}' created.")
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
@app.get("/users/me/", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

# Secure endpoint to create a new product
@app.post("/products/", response_model=schemas.Product)
def create_product(product: schemas.ProductBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(admin_required)):
    return crud.create_product(db=db, product=product)

# Public endpoint to get a list of products
@app.get("/products/", response_model=List[schemas.Product])
def read_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session)):
    products = crud.get_products(db, skip=skip, limit=limit)
    return products

@app.get("/products/{product_id}", response_model=schemas.Product)
def get_product(product_id: int, db: Session = Depends(get_db_session)):
    db_product = crud.get_product(db, product_id=product_id)
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

@app.post("/product_media/", response_model=schemas.ProductMedia)
def create_product_media(
    media: schemas.ProductMediaCreate,
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),
):
    # Optionally, check if product exists here.
    return crud.create_product_media(db=db, media=media)

# Get all media for a product (public)
@app.get("/product_media/product/{product_id}", response_model=List[schemas.ProductMedia])
def get_media_for_product(
    product_id: int,
    db: Session = Depends(get_db_session),
):
    return crud.get_media_for_product(db=db, product_id=product_id)

# Delete a ProductMedia entry (admin only)
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
    media_type: str = Form(...),  # "image" or "model"
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: models.User = Depends(admin_required),  # Admin only
):
    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    db_media = models.ProductMedia(
        product_id=product_id,
        media_type=media_type,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        data=file_bytes
    )
    db.add(db_media)
    db.commit()
    db.refresh(db_media)
    return db_media

@app.get("/media/{media_id}")
def get_media_file(media_id: int, db: Session = Depends(get_db_session)):
    media = db.query(models.ProductMedia).filter(models.ProductMedia.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return Response(
        content=media.data,
        media_type=media.content_type,
        headers={"Content-Disposition": f"inline; filename={media.filename}"}
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

# Secure endpoint to create a new order
@app.post("/orders/", response_model=schemas.Order)
def create_order(order: schemas.OrderBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.create_order(db=db, order=order)

# Public endpoint to get a list of orders (usually this would be secure, but depends on your needs)
@app.get("/orders/", response_model=List[schemas.Order])
def read_orders(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session)):
    orders = crud.get_orders(db, skip=skip, limit=limit)
    return orders

@app.post("/guest_orders/", response_model=schemas.Order)
def create_guest_order(order: schemas.GuestOrderBase, db: Session = Depends(get_db_session)):
    return crud.create_guest_order(db=db, order=order)

# PayPal integration endpoints
@app.post("/paypal/order/{order_id}")
def create_paypal_order(order_id: int, db: Session = Depends(get_db_session)):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    res = paypal.create_order(
        amount=float(order.total_cost),
        return_url=os.getenv("PAYPAL_RETURN_URL", "https://example.com/success"),
        cancel_url=os.getenv("PAYPAL_CANCEL_URL", "https://example.com/cancel"),
    )
    crud.set_paypal_order_id(db, order_id, res.get("id"))
    return res


@app.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(get_db_session)):
    body = await request.json()
    if not paypal.verify_webhook(request.headers, body):
        raise HTTPException(status_code=400, detail="Invalid webhook")
    event_type = body.get("event_type")
    if event_type == "CHECKOUT.ORDER.APPROVED":
        order_id = body["resource"]["id"]
        order = crud.get_order_by_paypal_id(db, order_id)
        if order:
            crud.update_order_status(db, order.id, "APPROVED")
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
    return crud.add_to_cart(db=db, cart=cart)

# Secure endpoint to view the cart of the current user
@app.get("/cart/", response_model=List[schemas.Cart])
def read_cart(db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.get_cart_items(db=db, user_id=current_user.id)

@app.put("/cart/{cart_id}", response_model=schemas.Cart)
def update_cart_item(cart_id: int, quantity: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.update_cart_item(db, cart_id, quantity)

@app.delete("/cart/{cart_id}", response_model=schemas.Cart)
def delete_cart_item(cart_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.delete_cart_item(db, cart_id)
