# Payment System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar sistema de monetización al bot de Telegram con prueba gratis, 3 planes de suscripción y pagos via Mercado Pago y PayPal.

**Architecture:** SQLite guarda usuarios/suscripciones/pagos. `db.py` maneja todo el acceso a datos. `payments.py` genera links de checkout externos. Flask recibe webhooks de MP y PayPal y actualiza la DB. El bot verifica acceso antes de cada análisis y expone comandos de gestión de suscripción.

**Tech Stack:** Python/Flask, python-telegram-bot>=21, SQLite3, mercadopago SDK v2, requests (PayPal Orders API v2), APScheduler (ya instalado)

---

### Task 1: Setup — dependencias, variables de entorno y base de datos (`src/db.py`)

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`
- Create: `src/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Agregar `mercadopago` a `requirements.txt`**

Reemplazar el contenido completo de `requirements.txt`:
```
flask
requests
python-dotenv
anthropic
pytest
python-telegram-bot[job-queue]>=21.0
APScheduler>=3.10
mercadopago
```

- [ ] **Step 2: Instalar dependencia**

```powershell
cd C:\Users\octav\football-predictor
pip install mercadopago
```

Esperado: instalación sin errores.

- [ ] **Step 3: Agregar variables al `.env`**

Agregar al final de `.env`:
```
MP_ACCESS_TOKEN=TEST-tu_access_token_aqui
MP_WEBHOOK_SECRET=tu_webhook_secret_aqui
PAYPAL_CLIENT_ID=tu_paypal_client_id_aqui
PAYPAL_CLIENT_SECRET=tu_paypal_client_secret_aqui
WEBHOOK_BASE_URL=https://web-production-61f66b.up.railway.app
DB_PATH=data/football.db
```

- [ ] **Step 4: Crear directorio de datos**

```powershell
mkdir C:\Users\octav\football-predictor\data
```

- [ ] **Step 5: Escribir tests que fallan**

Crear `tests/test_db.py`:

```python
import sys, os, tempfile, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")

def test_init_db_creates_tables(db_path):
    from db import init_db, get_connection
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "users" in tables
    assert "subscriptions" in tables
    assert "payments" in tables
    conn.close()

def test_get_or_create_user_creates_new(db_path):
    from db import init_db, get_or_create_user, get_connection
    init_db(db_path)
    get_or_create_user(db_path, 12345, "testuser", "Test")
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM users WHERE telegram_id=12345").fetchone()
    assert row is not None
    assert row["trial_used"] == 0
    conn.close()

def test_get_or_create_user_idempotent(db_path):
    from db import init_db, get_or_create_user
    init_db(db_path)
    get_or_create_user(db_path, 12345, "testuser", "Test")
    get_or_create_user(db_path, 12345, "testuser", "Test")  # segunda vez no debe fallar

def test_can_analyze_trial_available(db_path):
    from db import init_db, get_or_create_user, can_analyze
    init_db(db_path)
    get_or_create_user(db_path, 12345, "user", "User")
    result, reason = can_analyze(db_path, 12345)
    assert result is True
    assert reason == "trial"

def test_can_analyze_trial_used(db_path):
    from db import init_db, get_or_create_user, use_trial, can_analyze
    init_db(db_path)
    get_or_create_user(db_path, 12345, "user", "User")
    use_trial(db_path, 12345)
    result, reason = can_analyze(db_path, 12345)
    assert result is False
    assert reason == "no_trial"

def test_can_analyze_active_subscription(db_path):
    from db import init_db, get_or_create_user, activate_subscription, can_analyze
    from datetime import datetime, timedelta
    init_db(db_path)
    get_or_create_user(db_path, 12345, "user", "User")
    expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
    activate_subscription(db_path, 12345, "pro", expires, "mercadopago")
    result, reason = can_analyze(db_path, 12345)
    assert result is True
    assert reason == "subscription"

def test_can_analyze_limit_reached(db_path):
    from db import init_db, get_or_create_user, activate_subscription, increment_analyses, can_analyze
    from datetime import datetime, timedelta
    init_db(db_path)
    get_or_create_user(db_path, 12345, "user", "User")
    expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
    activate_subscription(db_path, 12345, "basic", expires, "mercadopago")
    # basic = 4/día, incrementar 4 veces
    for _ in range(4):
        increment_analyses(db_path, 12345)
    result, reason = can_analyze(db_path, 12345)
    assert result is False
    assert reason == "limit_reached"

def test_plan_limits():
    from db import PLAN_LIMITS
    assert PLAN_LIMITS["basic"] == 4
    assert PLAN_LIMITS["pro"] == 7
    assert PLAN_LIMITS["unlimited"] is None
```

- [ ] **Step 6: Ejecutar para verificar que fallan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_db.py -v
```

Esperado: `ImportError: No module named 'db'`

- [ ] **Step 7: Crear `src/db.py`**

```python
import sqlite3
import os
from datetime import datetime, date

PLAN_LIMITS = {
    "basic": 4,
    "pro": 7,
    "unlimited": None,
}

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str) -> None:
    """Crea las tablas si no existen."""
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            trial_used  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id       INTEGER NOT NULL,
            plan              TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'active',
            analyses_today    INTEGER DEFAULT 0,
            last_reset_date   TEXT,
            starts_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at        DATETIME NOT NULL,
            payment_provider  TEXT,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id  TEXT UNIQUE,
            telegram_id INTEGER NOT NULL,
            plan        TEXT NOT NULL,
            amount_usd  REAL NOT NULL,
            provider    TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        );
    """)
    conn.commit()
    conn.close()

def get_or_create_user(db_path: str, telegram_id: int, username: str, first_name: str) -> None:
    """Registra un usuario nuevo si no existe."""
    conn = get_connection(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
        (telegram_id, username, first_name)
    )
    conn.commit()
    conn.close()

def use_trial(db_path: str, telegram_id: int) -> None:
    """Marca la prueba gratuita como usada."""
    conn = get_connection(db_path)
    conn.execute("UPDATE users SET trial_used=1 WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()

def activate_subscription(db_path: str, telegram_id: int, plan: str,
                           expires_at: str, provider: str) -> None:
    """Activa o renueva la suscripción de un usuario."""
    conn = get_connection(db_path)
    # Cancelar suscripciones anteriores activas
    conn.execute(
        "UPDATE subscriptions SET status='cancelled' WHERE telegram_id=? AND status='active'",
        (telegram_id,)
    )
    conn.execute(
        """INSERT INTO subscriptions (telegram_id, plan, status, expires_at, payment_provider)
           VALUES (?, ?, 'active', ?, ?)""",
        (telegram_id, plan, expires_at, provider)
    )
    conn.commit()
    conn.close()

def increment_analyses(db_path: str, telegram_id: int) -> None:
    """Incrementa el contador de análisis del día."""
    today = date.today().isoformat()
    conn = get_connection(db_path)
    conn.execute(
        """UPDATE subscriptions SET analyses_today = analyses_today + 1, last_reset_date = ?
           WHERE telegram_id=? AND status='active'""",
        (today, telegram_id)
    )
    conn.commit()
    conn.close()

def reset_daily_analyses(db_path: str) -> None:
    """Resetea el contador diario para todos los suscriptores activos."""
    today = date.today().isoformat()
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE subscriptions SET analyses_today=0, last_reset_date=? WHERE status='active'",
        (today,)
    )
    conn.commit()
    conn.close()

def can_analyze(db_path: str, telegram_id: int) -> tuple:
    """
    Verifica si el usuario puede hacer un análisis.
    Retorna (bool, razón).
    razón: 'trial' | 'subscription' | 'no_trial' | 'limit_reached' | 'expired'
    """
    today = date.today().isoformat()
    conn = get_connection(db_path)

    # Verificar suscripción activa
    sub = conn.execute(
        """SELECT plan, analyses_today, expires_at, last_reset_date
           FROM subscriptions WHERE telegram_id=? AND status='active'
           ORDER BY starts_at DESC LIMIT 1""",
        (telegram_id,)
    ).fetchone()

    if sub:
        # Verificar si venció
        if sub["expires_at"] < datetime.utcnow().isoformat():
            conn.execute(
                "UPDATE subscriptions SET status='expired' WHERE telegram_id=? AND status='active'",
                (telegram_id,)
            )
            conn.commit()
            conn.close()
            return False, "expired"

        plan = sub["plan"]
        limit = PLAN_LIMITS.get(plan)

        if limit is None:  # unlimited
            conn.close()
            return True, "subscription"

        # Resetear contador si es un día nuevo
        analyses_today = sub["analyses_today"]
        if sub["last_reset_date"] != today:
            analyses_today = 0

        if analyses_today < limit:
            conn.close()
            return True, "subscription"
        else:
            conn.close()
            return False, "limit_reached"

    # Sin suscripción activa — verificar trial
    user = conn.execute(
        "SELECT trial_used FROM users WHERE telegram_id=?", (telegram_id,)
    ).fetchone()
    conn.close()

    if user and user["trial_used"] == 0:
        return True, "trial"
    return False, "no_trial"

def get_subscription_info(db_path: str, telegram_id: int) -> dict | None:
    """Retorna info de la suscripción activa o None."""
    today = date.today().isoformat()
    conn = get_connection(db_path)
    sub = conn.execute(
        """SELECT plan, status, analyses_today, last_reset_date, expires_at, payment_provider
           FROM subscriptions WHERE telegram_id=? AND status='active'
           ORDER BY starts_at DESC LIMIT 1""",
        (telegram_id,)
    ).fetchone()
    user = conn.execute(
        "SELECT trial_used FROM users WHERE telegram_id=?", (telegram_id,)
    ).fetchone()
    conn.close()

    if not sub:
        return None

    analyses_today = sub["analyses_today"]
    if sub["last_reset_date"] != today:
        analyses_today = 0

    return {
        "plan": sub["plan"],
        "status": sub["status"],
        "analyses_today": analyses_today,
        "limit": PLAN_LIMITS.get(sub["plan"]),
        "expires_at": sub["expires_at"],
        "provider": sub["payment_provider"],
    }

def add_payment(db_path: str, payment_id: str, telegram_id: int,
                plan: str, amount_usd: float, provider: str) -> None:
    """Registra un pago pendiente."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO payments (payment_id, telegram_id, plan, amount_usd, provider)
           VALUES (?, ?, ?, ?, ?)""",
        (payment_id, telegram_id, plan, amount_usd, provider)
    )
    conn.commit()
    conn.close()

def approve_payment(db_path: str, payment_id: str) -> dict | None:
    """Marca un pago como aprobado y retorna los datos del pago."""
    conn = get_connection(db_path)
    payment = conn.execute(
        "SELECT * FROM payments WHERE payment_id=?", (payment_id,)
    ).fetchone()
    if not payment:
        conn.close()
        return None
    conn.execute(
        "UPDATE payments SET status='approved' WHERE payment_id=?", (payment_id,)
    )
    conn.commit()
    conn.close()
    return dict(payment)

def get_payment_history(db_path: str, telegram_id: int, limit: int = 10) -> list:
    """Retorna el historial de pagos del usuario."""
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT payment_id, plan, amount_usd, provider, status, created_at
           FROM payments WHERE telegram_id=? ORDER BY created_at DESC LIMIT ?""",
        (telegram_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 8: Ejecutar tests para verificar que pasan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_db.py -v
```

Esperado: 8 tests PASS.

- [ ] **Step 9: Ejecutar todos los tests**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS.

- [ ] **Step 10: Commit**

```powershell
git -C C:\Users\octav\football-predictor add requirements.txt src/db.py tests/test_db.py data/.gitkeep
git -C C:\Users\octav\football-predictor commit -m "feat: add sqlite database module for users, subscriptions and payments"
```

---

### Task 2: Crear `src/payments.py` — generación de links de pago

**Files:**
- Create: `src/payments.py`
- Create: `tests/test_payments.py`

- [ ] **Step 1: Escribir tests que fallan**

Crear `tests/test_payments.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import patch, MagicMock

PLAN_PRICES = {"basic": 5.0, "pro": 10.0, "unlimited": 20.0}
PLAN_NAMES = {"basic": "Plan Básico", "pro": "Plan Pro", "unlimited": "Plan Ilimitado"}

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
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_payments.py -v
```

Esperado: `ImportError: No module named 'payments'`

- [ ] **Step 3: Crear `src/payments.py`**

```python
import os, requests
import mercadopago
from dotenv import load_dotenv

load_dotenv()

PLAN_PRICES = {"basic": 5.0, "pro": 10.0, "unlimited": 20.0}
PLAN_NAMES  = {"basic": "Plan Básico", "pro": "Plan Pro", "unlimited": "Plan Ilimitado"}

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

PAYPAL_BASE = "https://api-m.paypal.com"  # producción

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
```

- [ ] **Step 4: Ejecutar tests para verificar que pasan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_payments.py -v
```

Esperado: 5 tests PASS.

- [ ] **Step 5: Ejecutar todos los tests**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS.

- [ ] **Step 6: Commit**

```powershell
git -C C:\Users\octav\football-predictor add src/payments.py tests/test_payments.py
git -C C:\Users\octav\football-predictor commit -m "feat: add payments module for mercadopago and paypal checkout links"
```

---

### Task 3: Agregar webhooks a `src/app.py`

**Files:**
- Modify: `src/app.py`
- Create: `tests/test_webhooks.py`

- [ ] **Step 1: Escribir tests que fallan**

Crear `tests/test_webhooks.py`:

```python
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
    from db import get_or_create_user, add_payment, get_connection
    get_or_create_user(db_file, 99999, "user", "User")
    add_payment(db_file, "PREF_TEST_123", 99999, "pro", 10.0, "mercadopago")

    payload = {
        "type": "payment",
        "data": {"id": "PAY_001"},
        "external_reference": "99999|pro",
    }
    # Mock the MP payment lookup
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
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_webhooks.py -v
```

Esperado: error de importación o 404.

- [ ] **Step 3: Agregar imports y endpoints en `src/app.py`**

En `src/app.py`, agregar imports al inicio (después de los existentes):

```python
import mercadopago
import requests as http_requests
from db import init_db, get_or_create_user, approve_payment, activate_subscription, add_payment
from payments import PLAN_PRICES
```

Y agregar estas funciones y endpoints antes del bloque `if __name__ == "__main__":`:

```python
# ── DB init ──────────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "data/football.db")
init_db(DB_PATH)


# ── Helpers de notificación ──────────────────────────────────────────────────

def notify_user_subscription_activated(telegram_id: int, plan: str) -> None:
    """Notifica al usuario por Telegram que su suscripción fue activada."""
    try:
        import asyncio
        from telegram import Bot
        from dotenv import load_dotenv
        load_dotenv()
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        plan_names = {"basic": "Básico 🥉", "pro": "Pro 🥈", "unlimited": "Ilimitado 🥇"}
        msg = (
            f"✅ *¡Suscripción activada!*\n\n"
            f"Plan: *{plan_names.get(plan, plan)}*\n"
            f"Ya podés pedir análisis tácticos con /partidos 🎯"
        )
        async def send():
            bot = Bot(token)
            await bot.send_message(chat_id=telegram_id, text=msg, parse_mode="Markdown")
        asyncio.run(send())
    except Exception as e:
        app.logger.error(f"Error notificando usuario {telegram_id}: {e}")


def _capture_paypal_order(order_id: str) -> bool:
    """Captura un order aprobado de PayPal."""
    try:
        from payments import _get_paypal_token, PAYPAL_BASE
        token = _get_paypal_token()
        resp = http_requests.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


# ── Webhooks ──────────────────────────────────────────────────────────────────

@app.route("/webhook/mercadopago", methods=["POST"])
def webhook_mercadopago():
    data = request.get_json(silent=True) or {}
    if data.get("type") != "payment":
        return jsonify({"status": "ignored"}), 200

    try:
        payment_data_id = data.get("data", {}).get("id")
        external_ref = data.get("external_reference", "")

        sdk = mercadopago.SDK(os.environ.get("MP_ACCESS_TOKEN", ""))
        payment_info = sdk.payment().get(payment_data_id)
        response = payment_info.get("response", {})

        if response.get("status") != "approved":
            return jsonify({"status": "not_approved"}), 200

        ext_ref = response.get("external_reference", external_ref)
        if "|" not in ext_ref:
            return jsonify({"status": "invalid_ref"}), 200

        telegram_id_str, plan = ext_ref.split("|", 1)
        telegram_id = int(telegram_id_str)
        payment_id = str(response.get("id", payment_data_id))

        payment = approve_payment(DB_PATH, payment_id)
        if not payment:
            add_payment(DB_PATH, payment_id, telegram_id, plan, PLAN_PRICES.get(plan, 0), "mercadopago")
            approve_payment(DB_PATH, payment_id)

        from datetime import datetime, timedelta
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
        activate_subscription(DB_PATH, telegram_id, plan, expires, "mercadopago")
        notify_user_subscription_activated(telegram_id, plan)

    except Exception as e:
        app.logger.error(f"Error en webhook MP: {e}")

    return jsonify({"status": "ok"}), 200


@app.route("/webhook/paypal", methods=["POST"])
def webhook_paypal():
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type", "")

    if event_type != "CHECKOUT.ORDER.APPROVED":
        return jsonify({"status": "ignored"}), 200

    try:
        resource = data.get("resource", {})
        order_id = resource.get("id", "")
        custom_id = resource.get("custom_id", "")

        if "|" not in custom_id:
            return jsonify({"status": "invalid_ref"}), 200

        telegram_id_str, plan = custom_id.split("|", 1)
        telegram_id = int(telegram_id_str)

        _capture_paypal_order(order_id)

        payment = approve_payment(DB_PATH, order_id)
        if not payment:
            add_payment(DB_PATH, order_id, telegram_id, plan, PLAN_PRICES.get(plan, 0), "paypal")
            approve_payment(DB_PATH, order_id)

        from datetime import datetime, timedelta
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
        activate_subscription(DB_PATH, telegram_id, plan, expires, "paypal")
        notify_user_subscription_activated(telegram_id, plan)

    except Exception as e:
        app.logger.error(f"Error en webhook PayPal: {e}")

    return jsonify({"status": "ok"}), 200


@app.route("/payment/success")
def payment_success():
    return "<h1>✅ Pago completado. Volvé a Telegram para activar tu plan.</h1>"

@app.route("/payment/failure")
def payment_failure():
    return "<h1>❌ El pago no pudo procesarse. Intentá de nuevo.</h1>"

@app.route("/payment/cancel")
def payment_cancel():
    return "<h1>Pago cancelado. Podés intentar de nuevo cuando quieras.</h1>"

@app.route("/payment/pending")
def payment_pending():
    return "<h1>⏳ Pago pendiente. Te notificaremos cuando se confirme.</h1>"
```

- [ ] **Step 4: Ejecutar tests**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_webhooks.py -v
```

Esperado: 3 tests PASS.

- [ ] **Step 5: Ejecutar todos los tests**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS.

- [ ] **Step 6: Commit**

```powershell
git -C C:\Users\octav\football-predictor add src/app.py tests/test_webhooks.py
git -C C:\Users\octav\football-predictor commit -m "feat: add mercadopago and paypal webhook endpoints to flask"
```

---

### Task 4: Crear `src/bot_subscription.py` — handlers de suscripción del bot

**Files:**
- Create: `src/bot_subscription.py`

No hay tests unitarios para handlers de Telegram (dependen de la API). Se verifica manualmente en Task 6.

- [ ] **Step 1: Crear `src/bot_subscription.py`**

```python
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.environ.get("DB_PATH", "data/football.db")
BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "https://web-production-61f66b.up.railway.app")

PLAN_LABELS = {
    "basic":     "🥉 Básico — 4 análisis/día — $5 USD/mes",
    "pro":       "🥈 Pro — 7 análisis/día — $10 USD/mes",
    "unlimited": "🥇 Ilimitado — Sin límite — $20 USD/mes",
}

PLAN_NAMES = {
    "basic": "Básico 🥉",
    "pro": "Pro 🥈",
    "unlimited": "Ilimitado 🥇",
}


async def cmd_suscribir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los planes disponibles."""
    keyboard = [
        [InlineKeyboardButton(PLAN_LABELS["basic"],     callback_data="plan|basic")],
        [InlineKeyboardButton(PLAN_LABELS["pro"],       callback_data="plan|pro")],
        [InlineKeyboardButton(PLAN_LABELS["unlimited"], callback_data="plan|unlimited")],
    ]
    await update.message.reply_text(
        "🎯 *Elegí tu plan*\n\n"
        "Accedé al análisis táctico completo + parlay sugerido para todos los partidos.\n\n"
        "_Los 3 primeros días son sin cargo si aún no usaste tu prueba gratis._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """El usuario eligió un plan: mostrar opciones de pago."""
    query = update.callback_query
    await query.answer()
    plan = query.data.split("|")[1]
    context.user_data["selected_plan"] = plan

    keyboard = [
        [InlineKeyboardButton("💳 Mercado Pago", callback_data=f"pagar|mp|{plan}")],
        [InlineKeyboardButton("💙 PayPal",        callback_data=f"pagar|paypal|{plan}")],
        [InlineKeyboardButton("🔙 Volver",        callback_data="volver_planes")],
    ]
    await query.edit_message_text(
        f"Plan seleccionado: *{PLAN_NAMES[plan]}*\n\n¿Cómo querés pagar?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_pagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera el link de pago y se lo envía al usuario."""
    query = update.callback_query
    await query.answer()
    _, provider, plan = query.data.split("|")
    telegram_id = update.effective_user.id

    await query.edit_message_text("⏳ Generando link de pago...")

    from db import get_or_create_user, add_payment
    from payments import create_mp_payment, create_paypal_payment

    get_or_create_user(DB_PATH, telegram_id,
                       update.effective_user.username or "",
                       update.effective_user.first_name or "")

    if provider == "mp":
        result = create_mp_payment(telegram_id, plan, BASE_URL)
    else:
        result = create_paypal_payment(telegram_id, plan, BASE_URL)

    if not result:
        await query.edit_message_text(
            "⚠️ No se pudo generar el link de pago. Intentá de nuevo en unos minutos."
        )
        return

    link, payment_id = result
    from payments import PLAN_PRICES
    add_payment(DB_PATH, payment_id, telegram_id, plan, PLAN_PRICES[plan], provider)

    provider_name = "Mercado Pago" if provider == "mp" else "PayPal"
    keyboard = [[InlineKeyboardButton(f"💳 Pagar con {provider_name}", url=link)]]
    await query.edit_message_text(
        f"✅ *Link de pago listo*\n\n"
        f"Plan: *{PLAN_NAMES[plan]}*\n"
        f"Hacé click para completar el pago. "
        f"Una vez confirmado, tu plan se activa automáticamente.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_volver_planes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volver al menú de planes."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(PLAN_LABELS["basic"],     callback_data="plan|basic")],
        [InlineKeyboardButton(PLAN_LABELS["pro"],       callback_data="plan|pro")],
        [InlineKeyboardButton(PLAN_LABELS["unlimited"], callback_data="plan|unlimited")],
    ]
    await query.edit_message_text(
        "🎯 *Elegí tu plan*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_mi_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado actual de la suscripción."""
    from db import get_or_create_user, get_subscription_info
    telegram_id = update.effective_user.id
    get_or_create_user(DB_PATH, telegram_id,
                       update.effective_user.username or "",
                       update.effective_user.first_name or "")

    info = get_subscription_info(DB_PATH, telegram_id)
    if not info:
        await update.message.reply_text(
            "📭 No tenés una suscripción activa.\n\nUsá /suscribir para ver los planes."
        )
        return

    limit_str = str(info["limit"]) if info["limit"] else "∞"
    used = info["analyses_today"]
    try:
        from datetime import datetime
        exp = datetime.fromisoformat(info["expires_at"]).strftime("%d/%m/%Y")
    except Exception:
        exp = info["expires_at"][:10]

    keyboard = [
        [InlineKeyboardButton("📋 Ver historial",  callback_data="historial")],
        [InlineKeyboardButton("🔄 Cambiar plan",   callback_data="cambiar_plan")],
        [InlineKeyboardButton("❌ Cancelar plan",  callback_data="cancelar_confirm")],
    ]
    await update.message.reply_text(
        f"📊 *Tu plan actual*\n\n"
        f"Plan: *{PLAN_NAMES.get(info['plan'], info['plan'])}*\n"
        f"Estado: ✅ Activo\n"
        f"Análisis hoy: {used}/{limit_str}\n"
        f"Se reinicia: a las 00:00 ART\n"
        f"Vence: {exp}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el historial de pagos."""
    from db import get_payment_history
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id
    history = get_payment_history(DB_PATH, telegram_id)

    if not history:
        await query.edit_message_text("📭 No tenés pagos registrados.")
        return

    lines = ["📋 *Historial de pagos*\n"]
    for p in history:
        status_icon = "✅" if p["status"] == "approved" else "⏳" if p["status"] == "pending" else "❌"
        date_str = p["created_at"][:10]
        lines.append(f"{status_icon} {PLAN_NAMES.get(p['plan'], p['plan'])} — ${p['amount_usd']} — {p['provider']} — {date_str}")

    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="volver_mi_plan")]]
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_cancelar_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pide confirmación para cancelar."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("✅ Sí, cancelar", callback_data="cancelar_ok")],
        [InlineKeyboardButton("🔙 No, volver",   callback_data="volver_mi_plan")],
    ]
    await query.edit_message_text(
        "⚠️ *¿Cancelar suscripción?*\n\n"
        "Seguirás teniendo acceso hasta que venza el período actual.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_cancelar_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la suscripción."""
    from db import get_connection
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id
    conn = get_connection(DB_PATH)
    conn.execute(
        "UPDATE subscriptions SET status='cancelled' WHERE telegram_id=? AND status='active'",
        (telegram_id,)
    )
    conn.commit()
    conn.close()
    await query.edit_message_text(
        "✅ Suscripción cancelada. Seguirás teniendo acceso hasta que venza tu período actual."
    )


async def cb_cambiar_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirige a la selección de plan."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(PLAN_LABELS["basic"],     callback_data="plan|basic")],
        [InlineKeyboardButton(PLAN_LABELS["pro"],       callback_data="plan|pro")],
        [InlineKeyboardButton(PLAN_LABELS["unlimited"], callback_data="plan|unlimited")],
    ]
    await query.edit_message_text(
        "🔄 *Cambiar plan*\n\nElegí tu nuevo plan:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cb_volver_mi_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vuelve a mostrar info del plan (reusa cmd_mi_plan con edit)."""
    query = update.callback_query
    await query.answer()
    from db import get_subscription_info
    telegram_id = update.effective_user.id
    info = get_subscription_info(DB_PATH, telegram_id)
    if not info:
        await query.edit_message_text("📭 No tenés suscripción activa. Usá /suscribir.")
        return
    limit_str = str(info["limit"]) if info["limit"] else "∞"
    try:
        from datetime import datetime
        exp = datetime.fromisoformat(info["expires_at"]).strftime("%d/%m/%Y")
    except Exception:
        exp = info["expires_at"][:10]
    keyboard = [
        [InlineKeyboardButton("📋 Ver historial",  callback_data="historial")],
        [InlineKeyboardButton("🔄 Cambiar plan",   callback_data="cambiar_plan")],
        [InlineKeyboardButton("❌ Cancelar plan",  callback_data="cancelar_confirm")],
    ]
    await query.edit_message_text(
        f"📊 *Tu plan actual*\n\n"
        f"Plan: *{PLAN_NAMES.get(info['plan'], info['plan'])}*\n"
        f"Estado: ✅ Activo\n"
        f"Análisis hoy: {info['analyses_today']}/{limit_str}\n"
        f"Vence: {exp}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
```

- [ ] **Step 2: Verificar sintaxis**

```powershell
cd C:\Users\octav\football-predictor
python -c "import ast; ast.parse(open('src/bot_subscription.py', encoding='utf-8').read()); print('OK')"
```

Esperado: `OK`

- [ ] **Step 3: Commit**

```powershell
git -C C:\Users\octav\football-predictor add src/bot_subscription.py
git -C C:\Users\octav\football-predictor commit -m "feat: add bot subscription handlers for plan selection and payment flow"
```

---

### Task 5: Integrar control de acceso y suscripción en `bot.py`

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Agregar imports de suscripción al inicio de `bot.py`**

En `bot.py`, después de los imports existentes de `bot_api` y `bot_formatter`, agregar:

```python
from db import init_db, get_or_create_user, can_analyze, use_trial, increment_analyses
from bot_subscription import (
    cmd_suscribir, cb_plan, cb_pagar, cb_volver_planes,
    cmd_mi_plan, cb_historial, cb_cancelar_confirm, cb_cancelar_ok,
    cb_cambiar_plan, cb_volver_mi_plan,
)
```

- [ ] **Step 2: Agregar inicialización de DB y constante DB_PATH**

Después de `load_dotenv()` en `bot.py`, agregar:

```python
DB_PATH = os.environ.get("DB_PATH", "data/football.db")
init_db(DB_PATH)
```

- [ ] **Step 3: Agregar partidos destacados para el trial**

Después de `MAX_AUTO_ANALISIS = 3`, agregar:

```python
# Ligas para el análisis de prueba gratis
LIGAS_TRIAL = ["Champions League", "Premier League", "La Liga", "Brasileirao", "Liga Argentina"]
MAX_TRIAL_FIXTURES = 5
```

- [ ] **Step 4: Modificar `cmd_start` para ofrecer el trial**

Reemplazar la función `cmd_start`:

```python
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    get_or_create_user(
        DB_PATH, telegram_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
    )
    _, reason = can_analyze(DB_PATH, telegram_id)

    if reason == "trial":
        # Mostrar partidos destacados para el trial
        await update.message.reply_text(
            "⚽ *¡Bienvenido a Football Predictor!*\n\n"
            "Tenés *1 análisis de prueba gratuito* disponible.\n"
            "Elegí un partido destacado de hoy para probarlo:",
            parse_mode="Markdown",
        )
        await _show_trial_fixtures(update, context)
    else:
        await update.message.reply_text(
            "⚽ *Football Predictor Bot*\n\n"
            "Comandos disponibles:\n"
            "/partidos — Ver partidos del día por liga\n"
            "/suscribir — Ver planes y suscribirte\n"
            "/mi_plan — Ver tu plan actual\n"
            "/ayuda — Mostrar esta ayuda",
            parse_mode="Markdown",
        )

async def _show_trial_fixtures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los partidos destacados disponibles para el trial."""
    trial_fixtures = []
    for league in LIGAS_TRIAL:
        fixtures = [f for f in get_fixtures(league) if not f.get("completed")]
        for f in fixtures[:2]:
            trial_fixtures.append((league, f))
        if len(trial_fixtures) >= MAX_TRIAL_FIXTURES:
            break

    if not trial_fixtures:
        await update.message.reply_text(
            "No hay partidos destacados disponibles ahora mismo.\n"
            "Usá /partidos para ver todos los partidos disponibles.\n"
            "Usá /suscribir para acceder al análisis completo."
        )
        return

    context.user_data["trial_fixtures"] = trial_fixtures
    keyboard = []
    for i, (league, f) in enumerate(trial_fixtures):
        label = f"{f['home_name']} vs {f['away_name']} ({league})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"trial|{i}")])

    await update.message.reply_text(
        "🎯 *Partidos destacados de hoy:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
```

- [ ] **Step 5: Agregar handler del trial**

Agregar esta función después de `_show_trial_fixtures`:

```python
async def cb_trial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """El usuario eligió un partido para su análisis de prueba."""
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id

    _, reason = can_analyze(DB_PATH, telegram_id)
    if reason != "trial":
        await query.edit_message_text(
            "⚠️ Ya usaste tu análisis de prueba. Usá /suscribir para continuar."
        )
        return

    idx = int(query.data.split("|")[1])
    trial_fixtures = context.user_data.get("trial_fixtures", [])
    if not trial_fixtures or idx >= len(trial_fixtures):
        await query.edit_message_text("⚠️ Datos expirados. Escribí /start para reintentar.")
        return

    league, f = trial_fixtures[idx]
    home_name = f["home_name"]
    away_name = f["away_name"]
    slug = _league_slug(league)

    await query.edit_message_text(
        f"⏳ Generando tu análisis de prueba para *{home_name} vs {away_name}*...\n"
        "_Esto puede tardar unos segundos_",
        parse_mode="Markdown",
    )

    analysis = get_analysis(league, slug, slug, str(f["home_id"]), str(f["away_id"]), home_name, away_name)
    if not analysis:
        await query.edit_message_text("⚠️ No se pudo obtener el análisis. Intentá con otro partido.")
        return

    insight = get_insight(analysis, home_name, away_name, str(f["home_id"]), str(f["away_id"]), slug, slug)
    if not insight:
        await query.edit_message_text("⚠️ Análisis táctico no disponible. Intentá con otro partido.")
        return

    # Marcar trial como usado
    use_trial(DB_PATH, telegram_id)

    text = format_insight_message(home_name, away_name, league, insight)
    keyboard = [[InlineKeyboardButton("🎯 Ver planes y suscribirme", callback_data="volver_planes")]]
    await query.edit_message_text(
        text + "\n\n_Este fue tu análisis de prueba gratuito._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
```

- [ ] **Step 6: Modificar `cb_partido` para verificar acceso**

Reemplazar el inicio de `cb_partido` hasta la línea del `await query.edit_message_text` de generación:

```python
async def cb_partido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """El usuario eligió un partido: verificar acceso y generar análisis táctico."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    get_or_create_user(
        DB_PATH, telegram_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
    )

    can, reason = can_analyze(DB_PATH, telegram_id)
    if not can:
        if reason == "no_trial":
            msg = "🔒 Ya usaste tu análisis gratuito.\n\nSuscribite para acceder al análisis completo:"
        elif reason == "limit_reached":
            msg = "🔒 Alcanzaste el límite de análisis de hoy.\n\nTu contador se reinicia a las 00:00 ART.\nO suscribite a un plan superior:"
        elif reason == "expired":
            msg = "🔒 Tu suscripción venció.\n\nRenovate para seguir accediendo:"
        else:
            msg = "🔒 Necesitás una suscripción para ver el análisis:"

        keyboard = [[InlineKeyboardButton("🎯 Ver planes", callback_data="volver_planes")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    idx = int(query.data.split("|")[1])
    fixtures = context.user_data.get("fixtures", [])
    league = context.user_data.get("league", "")

    if not fixtures or idx >= len(fixtures):
        await query.edit_message_text("⚠️ Datos expirados. Intentá de nuevo con /partidos.")
        return

    f = fixtures[idx]
    home_id = str(f["home_id"])
    away_id = str(f["away_id"])
    home_name = f["home_name"]
    away_name = f["away_name"]
    slug = _league_slug(league)

    await query.edit_message_text(
        f"⏳ Generando análisis para *{home_name} vs {away_name}*...\n"
        "_Esto puede tardar unos segundos_",
        parse_mode="Markdown",
    )

    analysis = get_analysis(league, slug, slug, home_id, away_id, home_name, away_name)
    if not analysis:
        await query.edit_message_text(
            f"⚠️ No se pudo obtener el análisis para *{home_name} vs {away_name}*.",
            parse_mode="Markdown",
        )
        return

    insight = get_insight(analysis, home_name, away_name, home_id, away_id, slug, slug)
    if not insight:
        await query.edit_message_text(
            f"⚠️ Análisis táctico no disponible para *{home_name} vs {away_name}*.",
            parse_mode="Markdown",
        )
        return

    # Incrementar contador si es suscriptor (no trial)
    if reason == "subscription":
        increment_analyses(DB_PATH, telegram_id)

    text = format_insight_message(home_name, away_name, league, insight)
    await query.edit_message_text(text, parse_mode="Markdown")
```

- [ ] **Step 7: Agregar reset diario al scheduler en `post_init`**

En la función `post_init`, después de `scheduler.add_job(publicar_partidos_del_dia, ...)`, agregar:

```python
    scheduler.add_job(
        lambda: reset_daily_analyses(DB_PATH),
        CronTrigger(hour=0, minute=0),
        id="reset_daily",
    )
```

Y agregar el import al inicio de `bot.py`:
```python
from db import init_db, get_or_create_user, can_analyze, use_trial, increment_analyses, reset_daily_analyses
```

- [ ] **Step 8: Registrar todos los handlers nuevos en `main()`**

En la función `main()`, después de los handlers existentes, agregar:

```python
    # Handlers de suscripción
    app.add_handler(CommandHandler("suscribir", cmd_suscribir))
    app.add_handler(CommandHandler("mi_plan", cmd_mi_plan))
    app.add_handler(CallbackQueryHandler(cb_trial,          pattern=r"^trial\|"))
    app.add_handler(CallbackQueryHandler(cb_plan,           pattern=r"^plan\|"))
    app.add_handler(CallbackQueryHandler(cb_pagar,          pattern=r"^pagar\|"))
    app.add_handler(CallbackQueryHandler(cb_volver_planes,  pattern=r"^volver_planes$"))
    app.add_handler(CallbackQueryHandler(cb_historial,      pattern=r"^historial$"))
    app.add_handler(CallbackQueryHandler(cb_cancelar_confirm, pattern=r"^cancelar_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_cancelar_ok,    pattern=r"^cancelar_ok$"))
    app.add_handler(CallbackQueryHandler(cb_cambiar_plan,   pattern=r"^cambiar_plan$"))
    app.add_handler(CallbackQueryHandler(cb_volver_mi_plan, pattern=r"^volver_mi_plan$"))
```

- [ ] **Step 9: Verificar sintaxis**

```powershell
cd C:\Users\octav\football-predictor
python -c "import ast; ast.parse(open('bot.py', encoding='utf-8').read()); print('OK')"
```

Esperado: `OK`

- [ ] **Step 10: Ejecutar todos los tests**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS.

- [ ] **Step 11: Commit**

```powershell
git -C C:\Users\octav\football-predictor add bot.py
git -C C:\Users\octav\football-predictor commit -m "feat: integrate subscription access control and trial flow into bot"
```

---

### Task 6: Configurar variables en Railway y verificación manual

**Files:** ninguno — solo configuración y prueba

- [ ] **Step 1: Agregar variables en Railway**

En railway.app → servicio **web** → Variables, agregar:
```
MP_ACCESS_TOKEN=tu_access_token_de_mercadopago
MP_WEBHOOK_SECRET=tu_webhook_secret
PAYPAL_CLIENT_ID=tu_paypal_client_id
PAYPAL_CLIENT_SECRET=tu_paypal_client_secret
WEBHOOK_BASE_URL=https://web-production-61f66b.up.railway.app
DB_PATH=data/football.db
```

En railway.app → servicio **bot** (football-predictor) → Variables, agregar las mismas variables.

- [ ] **Step 2: Agregar volumen persistente para la DB en Railway**

En railway.app → servicio **web** → Settings → Volumes:
- Mount path: `/app/data`
- Esto asegura que la DB SQLite persiste entre deploys

Repetir para el servicio **bot**.

- [ ] **Step 3: Push y verificar deploy**

```powershell
git -C C:\Users\octav\football-predictor push
```

Verificar en Railway que ambos servicios deployaron sin errores.

- [ ] **Step 4: Probar el flujo de trial**

En Telegram, escribir `/start` al bot `@Fut_Analisis_Bot`. Verificar:
- Aparece bienvenida con lista de partidos destacados
- Al tocar un partido → genera análisis de prueba
- Al finalizar → aparece botón para ver planes

- [ ] **Step 5: Probar /suscribir**

Escribir `/suscribir`. Verificar:
- Aparecen los 3 planes con precios
- Al tocar un plan → aparecen opciones de pago (MP y PayPal)
- Al tocar un proveedor → aparece el link de pago

- [ ] **Step 6: Probar /mi_plan**

Escribir `/mi_plan`. Verificar:
- Sin suscripción → mensaje indicando que use /suscribir
- Con suscripción activa → muestra plan, análisis usados, fecha de vencimiento, botones de gestión

- [ ] **Step 7: Commit final**

```powershell
git -C C:\Users\octav\football-predictor push
```
