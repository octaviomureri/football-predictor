import os, requests
import mercadopago
from dotenv import load_dotenv

load_dotenv()

PLAN_PRICES = {"basic": 5.0, "pro": 10.0, "unlimited": 20.0}
PLAN_NAMES  = {"basic": "Plan Básico", "pro": "Plan Pro", "unlimited": "Plan Ilimitado"}

PAYPAL_BASE = "https://api-m.paypal.com"  # producción

# ── Mercado Pago ──────────────────────────────────────────────────────────────

def create_mp_payment(telegram_id: int, plan: str, base_url: str) -> tuple | None:
    """
    Genera un link de checkout de Mercado Pago.
    Retorna (checkout_url, preference_id) o None si falla.
    """
    try:
        sdk = mercadopago.SDK(os.environ.get("MP_ACCESS_TOKEN", ""))
        preference_data = {
            "items": [{
                "title": PLAN_NAMES[plan],
                "quantity": 1,
                "unit_price": PLAN_PRICES[plan],
                "currency_id": "USD",
            }],
            "external_reference": f"{telegram_id}|{plan}",
            "notification_url": f"{base_url}/webhook/mercadopago",
            "back_urls": {
                "success": f"{base_url}/payment/success",
                "failure": f"{base_url}/payment/failure",
                "pending": f"{base_url}/payment/pending",
            },
            "auto_return": "approved",
        }
        response = sdk.preference().create(preference_data)
        data = response["response"]
        return data["init_point"], data["id"]
    except Exception:
        return None


# ── PayPal ────────────────────────────────────────────────────────────────────

def _get_paypal_token() -> str:
    """Obtiene access token de PayPal."""
    client_id = os.environ.get("PAYPAL_CLIENT_ID", "")
    client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "")
    resp = requests.post(
        f"{PAYPAL_BASE}/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def create_paypal_payment(telegram_id: int, plan: str, base_url: str) -> tuple | None:
    """
    Genera un link de checkout de PayPal (Orders API v2).
    Retorna (approve_url, order_id) o None si falla.
    """
    try:
        token = _get_paypal_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {"currency_code": "USD", "value": f"{PLAN_PRICES[plan]:.2f}"},
                "description": PLAN_NAMES[plan],
                "custom_id": f"{telegram_id}|{plan}",
            }],
            "application_context": {
                "return_url": f"{base_url}/webhook/paypal/return",
                "cancel_url": f"{base_url}/payment/cancel",
                "brand_name": "Análisis Deportivo",
                "user_action": "PAY_NOW",
            },
        }
        resp = requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers=headers,
            json=payload,
            timeout=10,
        )
        data = resp.json()
        order_id = data["id"]
        approve_url = next(
            l["href"] for l in data["links"] if l["rel"] == "approve"
        )
        return approve_url, order_id
    except Exception:
        return None
