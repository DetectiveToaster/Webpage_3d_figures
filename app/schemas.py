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

class Model3DMediaBase(BaseModel):
    model3d_id: int
    media_type: str
    filename: str
    content_type: str

class Model3DMediaCreate(Model3DMediaBase):
    pass

class Model3DMedia(Model3DMediaBase):
    id: int
    class Config:
        orm_mode = True


class Model3DBase(BaseModel):
    height: float
    length: float
    width: float


class Model3DCreate(Model3DBase):
    product_id: int


class Model3D(Model3DBase):
    id: int
    product_id: int
    media: List[Model3DMedia] = []

    class Config:
        orm_mode = True


class ProductBase(BaseModel):
    name: str
    product_type: str
    quantity: int
    price: float
    discount: Optional[float] = None
    discounted_price: Optional[float] = None


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: int
    created_at: datetime
    model3d: Optional[Model3D] = None

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
    product_id: int
    quantity: int

class OrderProduct(OrderProductBase):
    order_id: int
    product_id: int

    class Config:
        orm_mode = True

class OrderBase(BaseModel):
    user_id: Optional[int]
    total_cost: float
    status: str
    paypal_order_id: Optional[str] = None

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
    paypal_order_id: Optional[str] = None
    products: List[OrderProductBase]

class Token(BaseModel):
    access_token: str
    token_type: str