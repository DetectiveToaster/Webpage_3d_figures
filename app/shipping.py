"""Shipping carrier client helpers for Correos, UPS, and DHL."""

from __future__ import annotations

import base64
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from . import schemas


def _default_timeout() -> float:
    value = os.getenv("SHIPPING_HTTP_TIMEOUT")
    if value is None:
        return 10.0
    try:
        return float(value)
    except ValueError:
        return 10.0


REQUEST_TIMEOUT = _default_timeout()
SUPPORTED_CARRIERS = ("correos", "ups", "dhl")


class ShippingAPIError(Exception):
    """Raised when a carrier API request fails or returns no usable quotes."""

    def __init__(self, carrier: str, message: str):
        self.carrier = carrier
        super().__init__(message)


def _decimalize(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _quantize_currency(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _safe_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str) and value.startswith("P") and value.endswith("D"):
        # Basic ISO8601 duration support for DHL style values (e.g. P3D)
        slice_value = value[1:-1]
        try:
            return int(slice_value)
        except ValueError:
            return None
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def _join_url(base: str, path: str) -> str:
    if not path:
        return base
    if base.endswith("/") and path.startswith("/"):
        return base[:-1] + path
    if not base.endswith("/") and not path.startswith("/"):
        return f"{base}/{path}"
    return base + path


def _basic_auth_value(token: str, secret: str) -> str:
    raw = f"{token}:{secret}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _common_payload(request: schemas.ShippingQuoteRequest) -> Dict[str, object]:
    return {
        "origin": request.origin.dict(),
        "destination": request.destination.dict(),
        "package": request.package.dict(),
        "declaredValue": request.declared_value,
        "currency": request.currency,
    }


def _request_json(url: str, payload: Dict[str, object], headers: Optional[Dict[str, str]], carrier: str) -> object:
    try:
        response = requests.post(url, json=payload, headers=headers or {}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ShippingAPIError(carrier, f"Request failed: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise ShippingAPIError(carrier, "Carrier response was not JSON") from exc


def _normalise_quotes(carrier: str, raw_items: Iterable[Dict[str, object]], fallback_currency: str) -> List[schemas.ShippingQuote]:
    quotes: List[schemas.ShippingQuote] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        price = (
            _decimalize(item.get("price"))
            or _decimalize(item.get("amount"))
            or _decimalize(item.get("importeTotal"))
            or _decimalize(item.get("totalPrice"))
            or _decimalize(item.get("monetaryValue"))
        )
        if price is None and "totalCharges" in item and isinstance(item["totalCharges"], dict):
            price = _decimalize(item["totalCharges"].get("monetaryValue"))
        if price is None and "TotalCharges" in item and isinstance(item["TotalCharges"], dict):
            price = _decimalize(item["TotalCharges"].get("MonetaryValue"))
        if price is None:
            continue
        currency = (
            item.get("currency")
            or item.get("currencyCode")
            or (item.get("totalCharges", {}).get("currencyCode") if isinstance(item.get("totalCharges"), dict) else None)
            or (item.get("TotalCharges", {}).get("CurrencyCode") if isinstance(item.get("TotalCharges"), dict) else None)
            or fallback_currency
        )
        service_value: Optional[object] = None
        for key in ("service", "serviceName", "producto", "productName"):
            candidate = item.get(key)
            if candidate:
                service_value = candidate
                break
        if service_value is None:
            service_data = item.get("Service")
            if isinstance(service_data, dict):
                service_value = service_data.get("Description") or service_data.get("Code")
            elif service_data is not None:
                service_value = service_data
        eta = (
            item.get("estimatedDeliveryDays")
            or item.get("plazoEntrega")
            or item.get("transitDays")
            or item.get("BusinessDaysInTransit")
            or item.get("deliveryTime")
        )
        normalised = schemas.ShippingQuote(
            carrier=carrier,
            service=str(service_value) if service_value else None,
            cost=float(_quantize_currency(price)),
            currency=str(currency) if currency else fallback_currency,
            estimated_delivery_days=_safe_int(eta),
            raw=item,
        )
        quotes.append(normalised)
    if not quotes:
        raise ShippingAPIError(carrier, "No rates were returned")
    return quotes


def _iterable_from_response(data: object, *keys: str) -> Iterable[Dict[str, object]]:
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [entry for entry in value if isinstance(entry, dict)]
            if isinstance(value, dict):
                return [value]
    return []


def _get_correos_quotes(request: schemas.ShippingQuoteRequest) -> List[schemas.ShippingQuote]:
    base_url = os.getenv("CORREOS_API_URL")
    if not base_url:
        raise ShippingAPIError("correos", "CORREOS_API_URL is not configured")
    endpoint = os.getenv("CORREOS_RATES_PATH", "/rates")
    token = os.getenv("CORREOS_API_KEY")
    headers: Dict[str, str] = {}
    if token:
        header_name = os.getenv("CORREOS_AUTH_HEADER", "Authorization")
        if header_name.lower() == "authorization":
            headers[header_name] = f"Bearer {token}"
        else:
            headers[header_name] = token
    payload = _common_payload(request)
    response = _request_json(_join_url(base_url, endpoint), payload, headers, "correos")
    items = list(_iterable_from_response(response, "tarifas", "rates", "services", "data"))
    if not items and isinstance(response, dict) and "tarifa" in response and isinstance(response["tarifa"], dict):
        items = [response["tarifa"]]
    if not items and isinstance(response, dict):
        items = [response]
    return _normalise_quotes("correos", items, request.currency)


def _get_ups_access_token() -> Optional[str]:
    direct = os.getenv("UPS_ACCESS_TOKEN")
    if direct:
        return direct
    client_id = os.getenv("UPS_CLIENT_ID")
    client_secret = os.getenv("UPS_CLIENT_SECRET")
    auth_url = os.getenv("UPS_AUTH_URL")
    if not (client_id and client_secret and auth_url):
        return None
    try:
        response = requests.post(
            auth_url,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            raise ShippingAPIError("ups", "UPS auth did not return an access token")
        return token
    except requests.RequestException as exc:
        raise ShippingAPIError("ups", f"UPS auth failed: {exc}") from exc
    except ValueError as exc:
        raise ShippingAPIError("ups", "UPS auth response was not JSON") from exc


def _get_ups_quotes(request: schemas.ShippingQuoteRequest) -> List[schemas.ShippingQuote]:
    base_url = os.getenv("UPS_API_URL")
    if not base_url:
        raise ShippingAPIError("ups", "UPS_API_URL is not configured")
    endpoint = os.getenv("UPS_RATES_PATH", "/rate")
    token = _get_ups_access_token()
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    username = os.getenv("UPS_USERNAME")
    password = os.getenv("UPS_PASSWORD")
    if username and password and not token:
        headers["Username"] = username
        headers["Password"] = password
    payload = _common_payload(request)
    response = _request_json(_join_url(base_url, endpoint), payload, headers, "ups")
    items: List[Dict[str, object]] = []
    if isinstance(response, dict):
        rated = response.get("RateResponse")
        if isinstance(rated, dict):
            shipment = rated.get("RatedShipment")
            if isinstance(shipment, list):
                items = [entry for entry in shipment if isinstance(entry, dict)]
            elif isinstance(shipment, dict):
                items = [shipment]
    if not items:
        items = list(_iterable_from_response(response, "rates", "services", "data"))
    if not items and isinstance(response, dict):
        items = [response]
    return _normalise_quotes("ups", items, request.currency)


def _parse_dhl_prices(product: Dict[str, object]) -> Optional[Decimal]:
    prices = product.get("totalPrice")
    if isinstance(prices, list) and prices:
        for candidate in prices:
            if isinstance(candidate, dict):
                value = _decimalize(candidate.get("price"))
                if value is not None:
                    return value
    return _decimalize(product.get("price"))


def _get_dhl_quotes(request: schemas.ShippingQuoteRequest) -> List[schemas.ShippingQuote]:
    base_url = os.getenv("DHL_API_URL")
    if not base_url:
        raise ShippingAPIError("dhl", "DHL_API_URL is not configured")
    endpoint = os.getenv("DHL_RATES_PATH", "/rates")
    token = os.getenv("DHL_API_KEY")
    secret = os.getenv("DHL_API_SECRET")
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if token and secret:
        headers["Authorization"] = f"Basic {_basic_auth_value(token, secret)}"
    elif token:
        headers["DHL-API-Key"] = token
    payload = _common_payload(request)
    response = _request_json(_join_url(base_url, endpoint), payload, headers, "dhl")
    items: List[Dict[str, object]] = []
    if isinstance(response, dict):
        products = response.get("products") or response.get("rates")
        if isinstance(products, list):
            items = [entry for entry in products if isinstance(entry, dict)]
    if not items and isinstance(response, list):
        items = [entry for entry in response if isinstance(entry, dict)]
    if not items and isinstance(response, dict):
        items = [response]
    normalised: List[schemas.ShippingQuote] = []
    for item in items:
        price = _parse_dhl_prices(item) or _decimalize(item.get("amount"))
        if price is None:
            continue
        currency = item.get("currency")
        total_price = item.get("totalPrice")
        if not currency and isinstance(total_price, list) and total_price:
            first = total_price[0]
            if isinstance(first, dict):
                currency = first.get("currency")
        normalised.append(
            schemas.ShippingQuote(
                carrier="dhl",
                service=str(item.get("productName") or item.get("serviceCode") or item.get("service")) if (
                    item.get("productName") or item.get("serviceCode") or item.get("service")
                ) else None,
                cost=float(_quantize_currency(price)),
                currency=str(currency) if currency else request.currency,
                estimated_delivery_days=_safe_int(item.get("deliveryTime") or item.get("deliveryDays")),
                raw=item,
            )
        )
    if not normalised:
        raise ShippingAPIError("dhl", "No rates were returned")
    return normalised


_HANDLER_MAP = {
    "correos": _get_correos_quotes,
    "ups": _get_ups_quotes,
    "dhl": _get_dhl_quotes,
}


def get_shipping_quotes(request: schemas.ShippingQuoteRequest) -> Tuple[List[schemas.ShippingQuote], Dict[str, str]]:
    carriers = request.carriers or list(SUPPORTED_CARRIERS)
    quotes: List[schemas.ShippingQuote] = []
    errors: Dict[str, str] = {}
    for carrier in carriers:
        key = carrier.lower()
        handler = _HANDLER_MAP.get(key)
        if handler is None:
            errors[carrier] = "Carrier not supported"
            continue
        try:
            quotes.extend(handler(request))
        except ShippingAPIError as exc:
            errors[carrier] = str(exc)
    return quotes, errors
