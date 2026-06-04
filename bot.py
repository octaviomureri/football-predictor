import os, sys, logging, asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from bot_api import get_fixtures, get_analysis, get_insight
from bot_formatter import format_fixtures_list, format_insight_message, format_no_fixtures
from db import init_db, get_or_create_user, can_analyze, use_trial, increment_analyses, reset_daily_analyses
from bot_subscription import (
    cmd_suscribir, cb_plan, cb_pagar, cb_volver_planes,
    cmd_mi_plan, cb_historial, cb_cancelar_confirm, cb_cancelar_ok,
    cb_cambiar_plan, cb_volver_mi_plan,
)

load_dotenv()

DB_PATH = os.environ.get("DB_PATH", "data/football.db")
init_db(DB_PATH)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# Ligas disponibles en el bot privado
LIGAS = [
    "Premier League", "La Liga", "Serie A",
    "Bundesliga", "Ligue 1", "Champions League",
    "Europa League", "Liga Argentina", "Brasileirao",
    "Copa Argentina", "Copa Libertadores",
    "Mundial", "Amistosos Internacionales",
]

# Ligas para publicación automática en el canal
LIGAS_CANAL = [
    "Premier League", "La Liga", "Champions League",
    "Liga Argentina", "Brasileirao",
]

# Máximo de partidos a analizar automáticamente por liga
MAX_AUTO_ANALISIS = 3

LIGAS_TRIAL = ["Champions League", "Premier League", "La Liga", "Brasileirao", "Liga Argentina"]
MAX_TRIAL_FIXTURES = 5


# ── Helpers ──────────────────────────────────────────────────────────────────

def _league_slug(league: str) -> str:
    """Retorna el slug ESPN/AF para una liga."""
    mapping = {
        "Premier League": "eng.1", "La Liga": "esp.1", "Serie A": "ita.1",
        "Bundesliga": "ger.1", "Ligue 1": "fra.1",
        "Champions League": "uefa.champions", "Europa League": "uefa.europa",
        "Liga Argentina": "arg.1", "Brasileirao": "bra.1",
        "Copa Argentina": "af:130", "Copa Libertadores": "conmebol.libertadores",
        "Mundial": "fifa.world", "Amistosos Internacionales": "fifa.friendly",
    }
    return mapping.get(league, "eng.1")

def _sanitise(s: str) -> str:
    """Elimina | de strings para evitar corrupción en callback_data."""
    return str(s).replace("|", "-")

def _fixture_callback(league: str, fixture: dict) -> str:
    """Genera el callback_data para un botón de partido."""
    slug = _league_slug(league)
    parts = [
        "partido", _sanitise(league),
        _sanitise(fixture["home_id"]), _sanitise(fixture["away_id"]),
        _sanitise(fixture["home_name"]), _sanitise(fixture["away_name"]),
        _sanitise(slug), _sanitise(slug),
    ]
    return "|".join(parts)


def _build_liga_keyboard() -> InlineKeyboardMarkup:
    """Construye el teclado inline de selección de liga."""
    keyboard, row = [], []
    for liga in LIGAS:
        row.append(InlineKeyboardButton(liga, callback_data=f"liga|{liga}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


# ── Handlers del bot privado ──────────────────────────────────────────────────

async def msg_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde automáticamente a cualquier mensaje que no sea un comando."""
    keyboard = [
        [InlineKeyboardButton("⚽ Ver partidos del día", callback_data="abrir_partidos")],
        [InlineKeyboardButton("🎯 Ver planes", callback_data="volver_planes")],
    ]
    await update.message.reply_text(
        "👋 ¡Hola! Para acceder a los análisis tácticos y predicciones usá los botones o los comandos:\n\n"
        "⚽ /partidos — Ver partidos del día\n"
        "🎯 /suscribir — Ver planes\n"
        "📊 /mi\\_plan — Tu suscripción actual",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def cb_abrir_partidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre el menú de ligas desde un botón."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "¿Qué liga querés ver?",
        reply_markup=_build_liga_keyboard(),
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    get_or_create_user(
        DB_PATH, telegram_id,
        update.effective_user.username or "",
        update.effective_user.first_name or "",
    )
    _, reason = can_analyze(DB_PATH, telegram_id)

    if reason == "trial":
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
            "Usá /partidos para ver todos los partidos.\n"
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

    use_trial(DB_PATH, telegram_id)

    text = format_insight_message(home_name, away_name, league, insight)
    keyboard = [[InlineKeyboardButton("🎯 Ver planes y suscribirme", callback_data="volver_planes")]]
    await query.edit_message_text(
        text + "\n\n_Este fue tu análisis de prueba gratuito._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)

async def cmd_partidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra teclado de selección de liga."""
    await update.message.reply_text(
        "¿Qué liga querés ver?",
        reply_markup=_build_liga_keyboard(),
    )

async def cb_liga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """El usuario eligió una liga: mostrar lista de partidos."""
    query = update.callback_query
    await query.answer()
    league = query.data.split("|", 1)[1]
    await query.edit_message_text(f"⏳ Cargando partidos de *{league}*...", parse_mode="Markdown")

    fixtures = [f for f in get_fixtures(league) if not f.get("completed")]
    if not fixtures:
        await query.edit_message_text(format_no_fixtures(league), parse_mode="Markdown")
        return

    # Guardar fixtures en user_data para evitar el límite de 64 bytes en callback_data
    context.user_data["fixtures"] = fixtures
    context.user_data["league"] = league

    text = format_fixtures_list(fixtures, league)
    keyboard = []
    for i, f in enumerate(fixtures):
        label = f"{f['home_name']} vs {f['away_name']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"partido|{i}")])
    keyboard.append([InlineKeyboardButton("🔙 Volver a ligas", callback_data="volver_ligas")])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

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

    if reason == "subscription":
        increment_analyses(DB_PATH, telegram_id)

    text = format_insight_message(home_name, away_name, league, insight)
    await query.edit_message_text(text, parse_mode="Markdown")

async def cb_volver_ligas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Volver al menú de selección de ligas."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "¿Qué liga querés ver?",
        reply_markup=_build_liga_keyboard(),
    )


# ── Publicación automática en canal ──────────────────────────────────────────

async def publicar_partidos_del_dia(bot):
    """Publica en el canal solo la lista de partidos del día por liga."""
    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL_ID no configurado, saltando publicación")
        return

    for league in LIGAS_CANAL:
        fixtures = [f for f in get_fixtures(league) if not f.get("completed")]
        if not fixtures:
            continue

        text = format_fixtures_list(fixtures, league)
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            logger.info(f"Publicados {len(fixtures)} partidos de {league}")
        except Exception as e:
            logger.error(f"Error publicando lista {league}: {e}")


async def publicar_promo(bot):
    """Cada 2 horas publica en el canal 3 partidos importantes con invitación al bot."""
    if not CHANNEL_ID:
        return

    # Recolectar hasta 3 partidos pendientes de las ligas principales
    destacados = []
    for league in LIGAS_TRIAL:
        fixtures = [f for f in get_fixtures(league) if not f.get("completed")]
        for f in fixtures[:1]:
            destacados.append((league, f))
        if len(destacados) >= 3:
            break

    try:
        if destacados:
            lines = [
                "🔥 *¿Querés los pronósticos para estos partidos?*\n",
            ]
            for league, f in destacados:
                from bot_formatter import _format_time
                time_str = _format_time(f.get("date", ""))
                time_part = f" — {time_str}" if time_str else ""
                lines.append(f"⚽ *{f['home_name']} vs {f['away_name']}*{time_part} ({league})")

            lines.append(
                "\n🧠 Análisis táctico, resultado probable, corners, amarillas y parlay sugerido.\n"
                "👉 Escribile a @Fut\\_Analisis\\_Bot y pedí el análisis de cualquier partido."
            )
            text = "\n".join(lines)
        else:
            text = (
                "⚽ *¿Buscás pronósticos de fútbol?*\n\n"
                "Hoy no hay partidos en curso, pero podés consultar estadísticas, "
                "análisis tácticos y parlays sugeridos para cualquier partido.\n\n"
                "👉 Escribile a @Fut\\_Analisis\\_Bot para más información."
            )

        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
        logger.info("Promo publicada en el canal")
    except Exception as e:
        logger.error(f"Error publicando promo: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def post_init(app: Application) -> None:
    """Inicia el scheduler después de que el event loop esté corriendo."""
    scheduler = AsyncIOScheduler(timezone="America/Argentina/Buenos_Aires")
    scheduler.add_job(
        publicar_partidos_del_dia,
        CronTrigger(hour=9, minute=0),
        args=[app.bot],
        id="publicar_9am",
    )
    scheduler.add_job(
        publicar_partidos_del_dia,
        CronTrigger(hour=12, minute=0),
        args=[app.bot],
        id="publicar_12pm",
    )
    scheduler.add_job(
        lambda: reset_daily_analyses(DB_PATH),
        CronTrigger(hour=0, minute=0),
        id="reset_daily",
    )
    # Promo cada 2 horas (10AM, 12PM, 2PM, 4PM, 6PM, 8PM, 10PM ART)
    scheduler.add_job(
        publicar_promo,
        CronTrigger(hour="10,12,14,16,18,20,22", minute=30),
        args=[app.bot],
        id="promo_2h",
    )
    scheduler.start()
    logger.info("Scheduler iniciado: partidos 9AM/12PM, promo cada 2h ART")


def main():
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN no configurado")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("partidos", cmd_partidos))
    app.add_handler(CallbackQueryHandler(cb_liga, pattern=r"^liga\|"))
    app.add_handler(CallbackQueryHandler(cb_partido, pattern=r"^partido\|"))
    app.add_handler(CallbackQueryHandler(cb_volver_ligas, pattern=r"^volver_ligas$"))

    # Handlers de suscripción
    app.add_handler(CommandHandler("suscribir", cmd_suscribir))
    app.add_handler(CommandHandler("mi_plan", cmd_mi_plan))
    app.add_handler(CallbackQueryHandler(cb_trial,            pattern=r"^trial\|"))
    app.add_handler(CallbackQueryHandler(cb_plan,             pattern=r"^plan\|"))
    app.add_handler(CallbackQueryHandler(cb_pagar,            pattern=r"^pagar\|"))
    app.add_handler(CallbackQueryHandler(cb_volver_planes,    pattern=r"^volver_planes$"))
    app.add_handler(CallbackQueryHandler(cb_historial,        pattern=r"^historial$"))
    app.add_handler(CallbackQueryHandler(cb_cancelar_confirm, pattern=r"^cancelar_confirm$"))
    app.add_handler(CallbackQueryHandler(cb_cancelar_ok,      pattern=r"^cancelar_ok$"))
    app.add_handler(CallbackQueryHandler(cb_cambiar_plan,     pattern=r"^cambiar_plan$"))
    app.add_handler(CallbackQueryHandler(cb_volver_mi_plan,   pattern=r"^volver_mi_plan$"))
    app.add_handler(CallbackQueryHandler(cb_abrir_partidos,   pattern=r"^abrir_partidos$"))

    # Auto-reply para mensajes que no son comandos
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_auto_reply))

    logger.info("Bot iniciado. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
