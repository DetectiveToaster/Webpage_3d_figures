from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Optional
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
    sort_order: int = 0
    path: Optional[str] = None


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
        extra = "allow"


class Product(ProductBase):
    id: int
    created_at: datetime
    view_count: int
    sold_count: int
    last_viewed_at: Optional[datetime] = None
    status: str = "published"
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
        extra = "allow"


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
    unit_price: Optional[float] = None
    currency: Optional[str] = None
    line_total: Optional[float] = None

class OrderProduct(OrderProductBase):
    order_id: int
    product_id: int

    class Config:
        orm_mode = True

class OrderBase(BaseModel):
    user_id: Optional[int]
    total_cost: float
    currency: str = "USD"
    status: str
    paypal_order_id: Optional[str] = None
    order_number: Optional[str] = None
    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_postal_code: Optional[str] = None
    shipping_country_code: Optional[str] = None

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
    currency: str = "USD"
    status: str
    paypal_order_id: Optional[str] = None
    order_number: Optional[str] = None
    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_postal_code: Optional[str] = None
    shipping_country_code: Optional[str] = None
    products: List[OrderProductBase]


# Upload session schemas
class UploadSession(BaseModel):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class UploadFile(BaseModel):
    id: int
    filename: str
    content_type: str
    role: Optional[str] = None
    sort_order: int = 0
    created_at: datetime

    class Config:
        orm_mode = True


class UploadSessionCreateResponse(BaseModel):
    upload_id: int


class UploadCommitItem(BaseModel):
    file_id: int
    product_id: int
    role: Optional[str] = None
    sort_order: int = 0
    kind: str


class UploadCommitRequest(BaseModel):
    items: List[UploadCommitItem]



class ShippingAddress(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
    postal_code: str
    city: str
    state: Optional[str] = None
    address_line1: str
    address_line2: Optional[str] = None


class ShippingPackage(BaseModel):
    weight_kg: float = Field(..., gt=0)
    length_cm: float = Field(..., gt=0)
    width_cm: float = Field(..., gt=0)
    height_cm: float = Field(..., gt=0)


class ShippingQuoteRequest(BaseModel):
    origin: ShippingAddress
    destination: ShippingAddress
    package: ShippingPackage
    declared_value: Optional[float] = Field(None, ge=0)
    currency: str = Field("EUR", min_length=3, max_length=3, description="ISO 4217 currency code")
    carriers: Optional[List[str]] = Field(None, description="Specific carriers to query; defaults to all supported carriers")

    @validator("currency")
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class ShippingQuote(BaseModel):
    carrier: str
    service: Optional[str] = None
    cost: float
    currency: str
    estimated_delivery_days: Optional[int] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class ShippingQuoteResponse(BaseModel):
    quotes: List[ShippingQuote] = Field(default_factory=list)
    errors: Dict[str, str] = Field(default_factory=dict)

class Token(BaseModel):
    access_token: str
    token_type: str
