from pydantic import BaseModel, Field
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

# Minimal profile for the current authenticated user
class UserProfile(BaseModel):
    id: int
    email: str
    is_admin: bool

    class Config:
        orm_mode = True

class Model3DMediaBase(BaseModel):
    # Deprecated in favor of ProductMedia
    pass

class Model3DMediaCreate(Model3DMediaBase):
    pass

class Model3DMedia(Model3DMediaBase):
    id: int
    class Config:
        orm_mode = True


class ProductMediaBase(BaseModel):
    product_id: int
    kind: str  # image | model | pdf
    filename: str
    content_type: str
    role: Optional[str] = None


class ProductMediaCreate(ProductMediaBase):
    pass


class ProductMedia(ProductMediaBase):
    id: int
    class Config:
        orm_mode = True


class ProductBase(BaseModel):
    name: str
    type: str = Field(..., alias="product_type")  # backward-compat input alias
    quantity: int
    price: float
    discount: Optional[float] = None
    discounted_price: Optional[float] = None
    is_visible: bool = True


class ProductCreate(ProductBase):
    class Config:
        allow_population_by_field_name = True


class Product(ProductBase):
    id: int
    created_at: datetime
    view_count: int
    sold_count: int
    last_viewed_at: Optional[datetime] = None
    # Optional subtype-specific fields
    height: Optional[float] = None
    length: Optional[float] = None
    width: Optional[float] = None

    series: Optional[str] = None
    rarity: Optional[str] = None
    condition: Optional[str] = None

    page_count: Optional[int] = None
    language: Optional[str] = None
    format: Optional[str] = None

    media: List[ProductMedia] = Field(default_factory=list)

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


# Admin field updates
class ProductVisibilityUpdate(BaseModel):
    is_visible: bool


class ProductPriceUpdate(BaseModel):
    price: float


class ProductDiscountUpdate(BaseModel):
    mode: str = Field(..., description="percent or amount")
    value: float = Field(..., description="percentage (0-100) or absolute amount")

class Product3DCreate(ProductBase):
    height: float
    length: float
    width: float

class CardCreate(ProductBase):
    series: Optional[str] = None
    rarity: Optional[str] = None
    condition: Optional[str] = None

class ManualCreate(ProductBase):
    page_count: Optional[int] = None
    language: Optional[str] = None
    format: Optional[str] = None

class CategoryBase(BaseModel):
    name: str

class Category(CategoryBase):
    id: int
    products: List[Product] = Field(default_factory=list)

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
    products: List[OrderProduct] = Field(default_factory=list)

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
