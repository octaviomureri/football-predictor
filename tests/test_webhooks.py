import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import pytest

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    from db import init_db
    init_db(db_file)
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c, db_file

def test_mp_webhook_approves_payment(client):
    c, db_file = client
    from db import get_or_create_user, add_payment
    get_or_create_user(db_file, 99999, "user", "User")
    add_payment(db_file, "PREF_TEST_123", 99999, "pro", 10.0, "mercadopago")

    payload = {
        "type": "payment",
        "data": {"id": "PAY_001"},
        "external_reference": "99999|pro",
    }
    import unittest.mock as mock
    mock_sdk = mock.MagicMock()
    mock_sdk.payment().get.return_value = {
        "response": {
            "status": "approved",
            "external_reference": "99999|pro",
            "id": "PAY_001",
        }
    }
    with mock.patch("app.mercadopago.SDK", return_value=mock_sdk), \
         mock.patch("app.notify_user_subscription_activated"):
        resp = c.post("/webhook/mercadopago",
                      data=json.dumps(payload),
                      content_type="application/json")
    assert resp.status_code == 200

def test_mp_webhook_ignores_non_payment(client):
    c, db_file = client
    payload = {"type": "merchant_order", "data": {"id": "123"}}
    resp = c.post("/webhook/mercadopago",
                  data=json.dumps(payload),
                  content_type="application/json")
    assert resp.status_code == 200

def test_paypal_webhook_captures_order(client):
    c, db_file = client
    from db import get_or_create_user, add_payment
    get_or_create_user(db_file, 88888, "user2", "User2")
    add_payment(db_file, "PP_ORDER_123", 88888, "basic", 5.0, "paypal")

    payload = {
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "PP_ORDER_123", "custom_id": "88888|basic"},
    }
    import unittest.mock as mock
    with mock.patch("app._capture_paypal_order", return_value=True), \
         mock.patch("app.notify_user_subscription_activated"):
        resp = c.post("/webhook/paypal",
                      data=json.dumps(payload),
                      content_type="application/json")
    assert resp.status_code == 200
