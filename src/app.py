import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify
from api_client import get_scoreboard, get_teams, search_teams_across_leagues, LEAGUES, get_team_injuries
from analyzer import analyze_match
from claude_insight import get_match_insight
import mercadopago
import requests as http_requests
from db import init_db, get_or_create_user, approve_payment, activate_subscription, add_payment
from payments import PLAN_PRICES

app = Flask(__name__, template_folder="../templates")

def _valid_slug(s):
    return s if (s and "." in s) else None

@app.route("/")
def index():
    return render_template("index.html", leagues=list(LEAGUES.keys()))

@app.route("/api/next-fixtures")
def next_fixtures():
    league_name = request.args.get("league", "Premier League")
    slug = LEAGUES[league_name]
    # Ligas af: van a API-Football, no tienen scoreboard en ESPN
    if slug.startswith("af:"):
        return jsonify([])
    try:
        data = get_scoreboard(slug, limit=15)
        events = data.get("events", [])
        result = []
        for e in events:
            comp = e.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            home = next((c for c in competitors if c["homeAway"] == "home"), None)
            away = next((c for c in competitors if c["homeAway"] == "away"), None)
            if not home or not away:
                continue
            status = comp.get("status", {}).get("type", {})
            result.append({
                "id": e["id"],
                "home_id": home["team"]["id"],
                "home_name": home["team"]["displayName"],
                "home_logo": home["team"].get("logo", ""),
                "away_id": away["team"]["id"],
                "away_name": away["team"]["displayName"],
                "away_logo": away["team"].get("logo", ""),
                "date": e.get("date", ""),
                "status": status.get("description", ""),
                "completed": status.get("completed", False),
            })
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/search-team")
def search():
    query = request.args.get("q", "")
    if len(query) < 2:
        return jsonify([])
    try:
        teams = search_teams_across_leagues(query)
        return jsonify(teams[:10])
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/analyze")
def analyze():
    league_name = request.args.get("league")
    home_id = request.args.get("home_id")
    away_id = request.args.get("away_id")
    home_name = request.args.get("home_name", "Local")
    away_name = request.args.get("away_name", "Visitante")
    home_slug = _valid_slug(request.args.get("home_slug", "")) or LEAGUES.get(league_name, "eng.1")
    away_slug = _valid_slug(request.args.get("away_slug", "")) or LEAGUES.get(league_name, "eng.1")

    try:
        result = analyze_match(home_slug, away_slug, home_id, away_id, home_name, away_name)
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/api/match-insight", methods=["POST"])
def match_insight():
    body = request.get_json(silent=True) or {}
    home_name = body.get("home_name", "Local")
    away_name = body.get("away_name", "Visitante")
    home_id = body.get("home_id")
    away_id = body.get("away_id")
    home_slug = body.get("home_slug", "eng.1")
    away_slug = body.get("away_slug", "eng.1")
    home_form = body.get("home_form", {})
    away_form = body.get("away_form", {})
    h2h = body.get("h2h", {})
    alerts = body.get("alerts", [])

    try:
        home_injured = get_team_injuries(home_id, home_slug)
        away_injured = get_team_injuries(away_id, away_slug)
        insight = get_match_insight(
            home_name=home_name,
            away_name=away_name,
            home_form=home_form,
            away_form=away_form,
            h2h=h2h,
            home_injured=home_injured,
            away_injured=away_injured,
            alerts=alerts,
        )
        return jsonify(insight)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


# ── DB init ──────────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "data/football.db")
init_db(DB_PATH)


# ── Helpers ───────────────────────────────────────────────────────────────────

def notify_user_subscription_activated(telegram_id: int, plan: str) -> None:
    """Notifica al usuario por Telegram que su suscripción fue activada."""
    try:
        import asyncio
        from telegram import Bot
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
