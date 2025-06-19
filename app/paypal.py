import os
import requests

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_BASE = os.getenv("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")


def _get_access_token():
    response = requests.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={"grant_type": "client_credentials"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_order(amount: float, return_url: str, cancel_url: str):
    token = _get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {"amount": {"currency_code": "USD", "value": f"{amount:.2f}"}}
        ],
        "application_context": {"return_url": return_url, "cancel_url": cancel_url},
    }
    r = requests.post(f"{PAYPAL_BASE}/v2/checkout/orders", json=payload, headers=headers)
    r.raise_for_status()
    return r.json()


def capture_order(order_id: str):
    token = _get_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    r = requests.post(f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture", headers=headers)
    r.raise_for_status()
    return r.json()


def verify_webhook(headers: dict, body: dict) -> bool:
    token = _get_access_token()
    payload = {
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "cert_url": headers.get("paypal-cert-url"),
        "auth_algo": headers.get("paypal-auth-algo"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": body,
    }
    verify_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    r = requests.post(
        f"{PAYPAL_BASE}/v1/notifications/verify-webhook-signature",
        json=payload,
        headers=verify_headers,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("verification_status") == "SUCCESS"
