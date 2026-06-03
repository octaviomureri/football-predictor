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

    fixtures = get_fixtures(league)
    if not fixtures:
        await query.edit_message_text(format_no_fixtures(league), parse_mode="Markdown")
        return

    text = format_fixtures_list(fixtures, league)
    keyboard = []
    for f in fixtures:
        label = f"{f['home_name']} vs {f['away_name']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=_fixture_callback(league, f))])
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

    parts = query.data.split("|")
    # partido|league|home_id|away_id|home_name|away_name|home_slug|away_slug
    if len(parts) != 8:
        await query.edit_message_text("⚠️ Datos inválidos. Intentá de nuevo con /partidos.")
        return
    _, league, home_id, away_id, home_name, away_name, home_slug, away_slug = parts

    await query.edit_message_text(
        f"⏳ Generando análisis para *{home_name} vs {away_name}*...\n"
        "_Esto puede tardar unos segundos_",
        parse_mode="Markdown",
    )

    analysis = get_analysis(league, home_slug, away_slug, home_id, away_id, home_name, away_name)
    if not analysis:
        await query.edit_message_text(
            f"⚠️ No se pudo obtener el análisis para *{home_name} vs {away_name}*.",
            parse_mode="Markdown",
        )
        return

    insight = get_insight(analysis, home_name, away_name, home_id, away_id, home_slug, away_slug)
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
    """Publica en el canal los partidos del día + análisis automático."""
    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL_ID no configurado, saltando publicación")
        return

    for league in LIGAS_CANAL:
        fixtures = get_fixtures(league)
        if not fixtures:
            continue

        # Publicar lista de partidos
        text = format_fixtures_list(fixtures, league)
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error publicando lista {league}: {e}")
            continue

        # Analizar los primeros MAX_AUTO_ANALISIS partidos
        slug = _league_slug(league)
        for fixture in fixtures[:MAX_AUTO_ANALISIS]:
            home_id = str(fixture["home_id"])
            away_id = str(fixture["away_id"])
            home_name = fixture["home_name"]
            away_name = fixture["away_name"]

            analysis = get_analysis(league, slug, slug, home_id, away_id, home_name, away_name)
            if not analysis:
                continue

            insight = get_insight(analysis, home_name, away_name, home_id, away_id, slug, slug)
            if not insight:
                continue

            msg = format_insight_message(home_name, away_name, league, insight)
            try:
                await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error publicando análisis {home_name} vs {away_name}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN no configurado")

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("partidos", cmd_partidos))
    app.add_handler(CallbackQueryHandler(cb_liga, pattern=r"^liga\|"))
    app.add_handler(CallbackQueryHandler(cb_partido, pattern=r"^partido\|"))
    app.add_handler(CallbackQueryHandler(cb_volver_ligas, pattern=r"^volver_ligas$"))

    # Scheduler: 9AM y 12PM hora Argentina (UTC-3)
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

    logger.info("Bot iniciado. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
