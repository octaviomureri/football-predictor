import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import patch, MagicMock

def test_plan_prices_defined():
    from payments import PLAN_PRICES, PLAN_NAMES
    assert PLAN_PRICES["basic"] == 5.0
    assert PLAN_PRICES["pro"] == 10.0
    assert PLAN_PRICES["unlimited"] == 20.0
    assert "basic" in PLAN_NAMES

def test_create_mp_payment_returns_link():
    from payments import create_mp_payment
    mock_sdk = MagicMock()
    mock_sdk.preference().create.return_value = {
        "response": {"init_point": "https://mp.com/checkout/123", "id": "PREF123"}
    }
    with patch("payments.mercadopago.SDK", return_value=mock_sdk):
        link, payment_id = create_mp_payment(12345, "pro", "https://base.url")
    assert "mp.com" in link
    assert payment_id == "PREF123"

def test_create_mp_payment_returns_none_on_error():
    from payments import create_mp_payment
    with patch("payments.mercadopago.SDK", side_effect=Exception("API error")):
        result = create_mp_payment(12345, "pro", "https://base.url")
    assert result is None

def test_create_paypal_payment_returns_link():
    from payments import create_paypal_payment
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "id": "PAYPAL123",
        "links": [
            {"rel": "self", "href": "https://api.paypal.com/self"},
            {"rel": "approve", "href": "https://paypal.com/checkoutnow?token=ABC"},
        ]
    }
    with patch("payments.requests.post", return_value=mock_response), \
         patch("payments._get_paypal_token", return_value="TOKEN123"):
        link, payment_id = create_paypal_payment(12345, "pro", "https://base.url")
    assert "paypal.com" in link
    assert payment_id == "PAYPAL123"

def test_create_paypal_payment_returns_none_on_error():
    from payments import create_paypal_payment
    with patch("payments._get_paypal_token", side_effect=Exception("Auth error")):
        result = create_paypal_payment(12345, "pro", "https://base.url")
    assert result is None
