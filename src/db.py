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

    sub = conn.execute(
        """SELECT plan, analyses_today, expires_at, last_reset_date
           FROM subscriptions WHERE telegram_id=? AND status='active'
           ORDER BY starts_at DESC LIMIT 1""",
        (telegram_id,)
    ).fetchone()

    if sub:
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

        if limit is None:
            conn.close()
            return True, "subscription"

        analyses_today = sub["analyses_today"]
        if sub["last_reset_date"] != today:
            analyses_today = 0

        if analyses_today < limit:
            conn.close()
            return True, "subscription"
        else:
            conn.close()
            return False, "limit_reached"

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
