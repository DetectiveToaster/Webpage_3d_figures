from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any, Dict, List, Optional
from datetime import datetime

class UserBase(BaseModel):
    email: str
    address: Optional[str] = None

    @field_validator("email")
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or not value.split("@", 1)[0] or not value.rsplit("@", 1)[-1]:
            raise ValueError("Invalid email address")
        return value

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=72)

class User(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Minimal profile for the current authenticated user
class UserProfile(BaseModel):
    id: int
    email: str
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)

class Model3DMediaBase(BaseModel):
    # Deprecated in favor of ProductMedia
    pass

class Model3DMediaCreate(Model3DMediaBase):
    pass

class Model3DMedia(Model3DMediaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: str = Field(..., alias="product_type")  # backward-compat input alias
    quantity: int = Field(..., ge=0)
    price: float = Field(..., ge=0)
    discount: Optional[float] = Field(None, ge=0)
    discounted_price: Optional[float] = Field(None, ge=0)
    is_visible: bool = True
    production_type: str = "in_stock"
    material: Optional[str] = None
    color: Optional[str] = None
    scale: Optional[str] = None
    estimated_production_days: Optional[int] = Field(None, ge=0)
    requires_manual_review: bool = False
    weight_grams: Optional[int] = Field(None, ge=0)

    @field_validator("production_type")
    def validate_production_type(cls, value: str) -> str:
        value = value.lower()
        if value not in {"in_stock", "made_to_order", "custom"}:
            raise ValueError("production_type must be in_stock, made_to_order, or custom")
        return value


class ProductCreate(ProductBase):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


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

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="allow")


# Admin field updates
class ProductVisibilityUpdate(BaseModel):
    is_visible: bool


class ProductPriceUpdate(BaseModel):
    price: float = Field(..., ge=0)


class ProductDiscountUpdate(BaseModel):
    mode: str = Field(..., description="percent or amount")
    value: float = Field(..., ge=0, description="percentage (0-100) or absolute amount")

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

    model_config = ConfigDict(from_attributes=True)

class OrderProductBase(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)
    unit_price: Optional[float] = None
    currency: Optional[str] = None
    line_total: Optional[float] = None


class OrderLineCreate(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class OrderAttachment(BaseModel):
    id: int
    order_id: int
    filename: str
    content_type: str
    role: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class OrderProduct(OrderProductBase):
    order_id: int
    product_id: int

    model_config = ConfigDict(from_attributes=True)

class OrderBase(BaseModel):
    user_id: Optional[int] = None
    subtotal: float = 0
    shipping_cost: float = 0
    total_cost: float
    currency: str = "USD"
    status: str
    payment_method: str = "bizum"
    payment_status: str = "PENDING"
    payment_reference: Optional[str] = None
    payment_instructions: Optional[str] = None
    paid_at: Optional[datetime] = None
    paypal_order_id: Optional[str] = None
    order_number: Optional[str] = None
    phone: Optional[str] = None
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None
    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_postal_code: Optional[str] = None
    shipping_country_code: Optional[str] = None
    tracking_number: Optional[str] = None
    shipping_carrier: Optional[str] = None
    shipped_at: Optional[datetime] = None


class CheckoutBase(BaseModel):
    currency: str = Field("USD", min_length=3, max_length=3)
    payment_method: str = "bizum"
    phone: Optional[str] = None
    customer_notes: Optional[str] = None
    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_postal_code: Optional[str] = None
    shipping_country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    products: List[OrderLineCreate]

    @field_validator("currency")
    def uppercase_checkout_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("payment_method")
    def validate_payment_method(cls, value: str) -> str:
        value = value.lower()
        if value not in {"bizum", "bank_transfer", "manual"}:
            raise ValueError("payment_method must be bizum, bank_transfer, or manual")
        return value

    @field_validator("shipping_country_code")
    def uppercase_country_code(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value


class OrderCreate(CheckoutBase):
    pass

class Order(OrderBase):
    id: int
    date: datetime
    products: List[OrderProduct] = Field(default_factory=list)
    attachments: List[OrderAttachment] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class CartBase(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class Cart(CartBase):
    id: int
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GuestOrderBase(CheckoutBase):
    guest_email: str
    guest_address: str

    @field_validator("guest_email")
    def normalise_guest_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or not value.split("@", 1)[0] or not value.rsplit("@", 1)[-1]:
            raise ValueError("Invalid email address")
        return value


class PaymentInstructions(BaseModel):
    payment_method: str
    payment_reference: str
    payment_instructions: str


class ManualShippingEstimateRequest(CheckoutBase):
    pass


class ManualShippingEstimate(BaseModel):
    subtotal: float
    shipping_cost: float
    total_cost: float
    currency: str
    estimated_delivery_days: Optional[int] = None


class OrderAdminUpdate(BaseModel):
    status: Optional[str] = None
    payment_status: Optional[str] = None
    payment_reference: Optional[str] = None
    admin_notes: Optional[str] = None
    tracking_number: Optional[str] = None
    shipping_carrier: Optional[str] = None


class ShippingRateRuleBase(BaseModel):
    name: str
    country_code: str = Field(..., min_length=2, max_length=2)
    postal_prefix: Optional[str] = None
    currency: str = Field("EUR", min_length=3, max_length=3)
    base_cost: float = Field(..., ge=0)
    per_item_cost: float = Field(0, ge=0)
    per_kg_cost: float = Field(0, ge=0)
    free_shipping_min_subtotal: Optional[float] = Field(None, ge=0)
    estimated_delivery_days: Optional[int] = Field(None, ge=0)
    is_active: bool = True

    @field_validator("country_code")
    def uppercase_rule_country_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("currency")
    def uppercase_rule_currency(cls, value: str) -> str:
        return value.upper()


class ShippingRateRuleCreate(ShippingRateRuleBase):
    pass


class ShippingRateRuleUpdate(BaseModel):
    name: Optional[str] = None
    country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    postal_prefix: Optional[str] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    base_cost: Optional[float] = Field(None, ge=0)
    per_item_cost: Optional[float] = Field(None, ge=0)
    per_kg_cost: Optional[float] = Field(None, ge=0)
    free_shipping_min_subtotal: Optional[float] = Field(None, ge=0)
    estimated_delivery_days: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @field_validator("country_code")
    def uppercase_optional_country_code(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value

    @field_validator("currency")
    def uppercase_optional_currency(cls, value: Optional[str]) -> Optional[str]:
        return value.upper() if value else value


class ShippingRateRule(ShippingRateRuleBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Upload session schemas
class UploadSession(BaseModel):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadFile(BaseModel):
    id: int
    filename: str
    content_type: str
    role: Optional[str] = None
    sort_order: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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

    @field_validator("currency")
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
