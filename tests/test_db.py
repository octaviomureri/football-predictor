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
