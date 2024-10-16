from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UserBase(BaseModel):
    email: str
    address: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class ProductBase(BaseModel):
    name: str
    production_cost: float
    selling_cost: float
    height: float
    length: float
    depth: float
    quantity: int

class Product(ProductBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

class CategoryBase(BaseModel):
    name: str

class Category(CategoryBase):
    id: int
    products: List[Product] = []

    class Config:
        orm_mode = True

class OrderProductBase(BaseModel):
    quantity: int

class OrderProduct(OrderProductBase):
    product_id: int

    class Config:
        orm_mode = True

class OrderBase(BaseModel):
    user_id: Optional[int]
    total_cost: float
    status: str

class Order(OrderBase):
    id: int
    date: datetime
    products: List[OrderProduct] = []

    class Config:
        orm_mode = True

class CartBase(BaseModel):
    user_id: int
    product_id: int
    quantity: int

class Cart(CartBase):
    id: int
    added_at: datetime

    class Config:
        orm_mode = True

class GuestOrderBase(BaseModel):
    guest_email: str
    guest_address: str
    total_cost: float
    status: str
    products: List[OrderProductBase]

class Token(BaseModel):
    access_token: str
    token_type: str