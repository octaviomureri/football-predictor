import os, sys, logging, asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from bot_api import get_fixtures, get_analysis, get_insight
from bot_formatter import format_fixtures_list, format_insight_message, format_no_fixtures

load_dotenv()

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

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ *Football Predictor Bot*\n\n"
        "Comandos disponibles:\n"
        "/partidos — Ver partidos del día por liga\n"
        "/ayuda — Mostrar esta ayuda",
        parse_mode="Markdown",
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
    """El usuario eligió un partido: generar análisis táctico."""
    query = update.callback_query
    await query.answer()

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
    scheduler.start()
    logger.info("Scheduler iniciado: publicaciones a las 9AM y 12PM ART")


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

    logger.info("Bot iniciado. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
