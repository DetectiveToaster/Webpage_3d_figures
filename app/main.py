# app/main.py

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordRequestForm
from typing import List
from . import crud, models, schemas, auth
from .database import SessionLocal, engine
from .auth import authenticate_user, create_access_token, get_current_active_user

# Initialize the database
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Dependency to get DB session
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
def create_product(product: schemas.ProductBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.create_product(db=db, product=product)

# Public endpoint to get a list of products
@app.get("/products/", response_model=List[schemas.Product])
def read_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db_session)):
    products = crud.get_products(db, skip=skip, limit=limit)
    return products

# Secure endpoint to update a product by ID
@app.put("/products/{product_id}", response_model=schemas.Product)
def update_product(product_id: int, product: schemas.ProductBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    db_product = crud.update_product(db=db, product_id=product_id, product=product)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Secure endpoint to delete a product by ID
@app.delete("/products/{product_id}", response_model=schemas.Product)
def delete_product(product_id: int, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    db_product = crud.delete_product(db=db, product_id=product_id)
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product

# Secure endpoint to create a new category
@app.post("/categories/", response_model=schemas.Category)
def create_category(category: schemas.CategoryBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
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

# Secure endpoint to add an item to the cart
@app.post("/cart/", response_model=schemas.Cart)
def add_to_cart(cart: schemas.CartBase, db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.add_to_cart(db=db, cart=cart)

# Secure endpoint to view the cart of the current user
@app.get("/cart/", response_model=List[schemas.Cart])
def read_cart(db: Session = Depends(get_db_session), current_user: models.User = Depends(get_current_active_user)):
    return crud.get_cart_items(db=db, user_id=current_user.id)
