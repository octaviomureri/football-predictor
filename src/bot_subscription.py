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
        "Accedé al análisis táctico completo + parlay sugerido para todos los partidos.",
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
    """Vuelve a mostrar info del plan."""
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
