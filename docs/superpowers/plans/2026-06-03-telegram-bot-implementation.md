# Telegram Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear un bot de Telegram con canal automático (9AM + 12PM) y bot privado interactivo que muestra partidos del día y genera análisis táctico + parlay llamando al Flask API existente.

**Architecture:** `bot.py` es un proceso independiente que usa `python-telegram-bot` para manejar comandos y callbacks inline, y `APScheduler` para las publicaciones automáticas. Llama al Flask API ya desplegado en Railway vía HTTP. Se agrega como segundo proceso en el `Procfile`.

**Tech Stack:** Python 3, python-telegram-bot>=21.0, APScheduler>=3.10, requests, python-dotenv

---

### Task 1: Setup — dependencias y variables de entorno

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`
- Modify: `Procfile`

- [ ] **Step 1: Agregar dependencias a `requirements.txt`**

Reemplazar el contenido completo de `requirements.txt`:
```
flask
requests
python-dotenv
anthropic
pytest
python-telegram-bot[job-queue]>=21.0
APScheduler>=3.10
```

- [ ] **Step 2: Instalar dependencias**

```powershell
cd C:\Users\octav\football-predictor
pip install "python-telegram-bot[job-queue]>=21.0" "APScheduler>=3.10"
```

Esperado: instalación sin errores.

- [ ] **Step 3: Agregar variables al `.env`**

Agregar al final de `.env`:
```
TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_CHANNEL_ID=@tu_canal_aqui
FLASK_API_URL=https://football-predictor.up.railway.app
```

Reemplazar los valores con los reales:
- `TELEGRAM_BOT_TOKEN`: token de @BotFather
- `TELEGRAM_CHANNEL_ID`: username del canal (ej: `@futbol_predictor`) o su ID numérico
- `FLASK_API_URL`: URL de Railway donde corre el Flask (sin slash final)

- [ ] **Step 4: Actualizar `Procfile`**

Reemplazar el contenido de `Procfile`:
```
web: python src/app.py
bot: python bot.py
```

- [ ] **Step 5: Commit**

```powershell
git -C C:\Users\octav\football-predictor add requirements.txt Procfile
git -C C:\Users\octav\football-predictor commit -m "chore: add telegram bot dependencies and procfile process"
```

---

### Task 2: Crear `bot_api.py` — cliente del Flask API

**Files:**
- Create: `src/bot_api.py`
- Create: `tests/test_bot_api.py`

Este módulo encapsula todas las llamadas HTTP al Flask API. El bot nunca llama `requests` directamente.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_bot_api.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import patch, MagicMock
from bot_api import get_fixtures, get_analysis, get_insight

LEAGUES = ["Premier League", "La Liga"]

def _mock_fixtures():
    return [
        {
            "id": "1", "home_id": "42", "away_id": "99",
            "home_name": "River Plate", "away_name": "Boca Juniors",
            "home_logo": "", "away_logo": "",
            "date": "2025-06-03T21:00:00Z", "status": "Scheduled", "completed": False
        }
    ]

def _mock_analysis():
    return {
        "prediction": {"best_bet": "Local", "confidence": 60, "prob_home": 55, "prob_draw": 25, "prob_away": 20,
                       "btts_prob": 45, "home_expected_goals": 1.5, "away_expected_goals": 0.9},
        "home_form": {"form": "WWDLL", "avg_goals_for": 1.8, "avg_goals_against": 1.1,
                      "avg_possession": 55.0, "avg_shots": 14.0, "avg_shots_on": 5.0,
                      "avg_fouls": 10.0, "avg_corners": 5.5, "avg_yellow_cards": 2.1,
                      "matches_analyzed": 10, "competitions_count": 2,
                      "top_scorers": [], "top_assists": [], "top_cards": []},
        "away_form": {"form": "WDLLL", "avg_goals_for": 1.2, "avg_goals_against": 1.4,
                      "avg_possession": 48.0, "avg_shots": 11.0, "avg_shots_on": 4.0,
                      "avg_fouls": 12.0, "avg_corners": 4.5, "avg_yellow_cards": 2.8,
                      "matches_analyzed": 10, "competitions_count": 2,
                      "top_scorers": [], "top_assists": [], "top_cards": []},
        "h2h": {"home_wins": 3, "away_wins": 2, "draws": 1, "total": 6},
        "mood_alerts": []
    }

def _mock_insight():
    return {
        "estilo_local": "River juega con posesión.",
        "estilo_visitante": "Boca presiona alto.",
        "desarrollo_partido": "Partido trabado en el medio.",
        "resultado_probable": "River 2-1 Boca",
        "corners": {"min": 8, "max": 11, "pick": 9.5},
        "amarillas": {"min": 3, "max": 5, "pick": 4.0},
        "parlay": {"picks": ["River gana", "Más de 9.5 corners"], "razon": "River dominante."}
    }

def test_get_fixtures_returns_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_fixtures()
    mock_resp.raise_for_status = MagicMock()
    with patch('bot_api.requests.get', return_value=mock_resp):
        result = get_fixtures("Liga Argentina")
    assert len(result) == 1
    assert result[0]["home_name"] == "River Plate"

def test_get_fixtures_returns_empty_on_error():
    with patch('bot_api.requests.get', side_effect=Exception("timeout")):
        result = get_fixtures("Liga Argentina")
    assert result == []

def test_get_analysis_returns_dict():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_analysis()
    mock_resp.raise_for_status = MagicMock()
    with patch('bot_api.requests.get', return_value=mock_resp):
        result = get_analysis("Liga Argentina", "arg.1", "arg.1", "42", "99", "River", "Boca")
    assert result["prediction"]["best_bet"] == "Local"

def test_get_analysis_returns_none_on_error():
    with patch('bot_api.requests.get', side_effect=Exception("timeout")):
        result = get_analysis("Liga Argentina", "arg.1", "arg.1", "42", "99", "River", "Boca")
    assert result is None

def test_get_insight_returns_dict():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_insight()
    mock_resp.raise_for_status = MagicMock()
    with patch('bot_api.requests.post', return_value=mock_resp):
        result = get_insight(_mock_analysis(), "River", "Boca", "42", "99", "arg.1", "arg.1")
    assert result["resultado_probable"] == "River 2-1 Boca"

def test_get_insight_returns_none_on_error():
    with patch('bot_api.requests.post', side_effect=Exception("timeout")):
        result = get_insight(_mock_analysis(), "River", "Boca", "42", "99", "arg.1", "arg.1")
    assert result is None
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_bot_api.py -v
```

Esperado: `ImportError: No module named 'bot_api'`

- [ ] **Step 3: Crear `src/bot_api.py`**

```python
import os, requests
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = 30

def _base_url():
    return os.environ.get("FLASK_API_URL", "http://localhost:5000").rstrip("/")

def get_fixtures(league: str) -> list:
    """Obtiene partidos del día para una liga. Retorna [] ante cualquier error."""
    try:
        resp = requests.get(
            f"{_base_url()}/api/next-fixtures",
            params={"league": league},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []

def get_analysis(league: str, home_slug: str, away_slug: str,
                 home_id: str, away_id: str, home_name: str, away_name: str) -> dict | None:
    """Llama /api/analyze. Retorna None ante cualquier error."""
    try:
        resp = requests.get(
            f"{_base_url()}/api/analyze",
            params={
                "league": league,
                "home_slug": home_slug,
                "away_slug": away_slug,
                "home_id": home_id,
                "away_id": away_id,
                "home_name": home_name,
                "away_name": away_name,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return None
        return data
    except Exception:
        return None

def get_insight(analysis: dict, home_name: str, away_name: str,
                home_id: str, away_id: str, home_slug: str, away_slug: str) -> dict | None:
    """Llama /api/match-insight con los datos del análisis. Retorna None ante cualquier error."""
    try:
        resp = requests.post(
            f"{_base_url()}/api/match-insight",
            json={
                "home_name": home_name,
                "away_name": away_name,
                "home_id": home_id,
                "away_id": away_id,
                "home_slug": home_slug,
                "away_slug": away_slug,
                "home_form": analysis.get("home_form", {}),
                "away_form": analysis.get("away_form", {}),
                "h2h": analysis.get("h2h", {}),
                "alerts": analysis.get("mood_alerts", []),
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return None
        return data
    except Exception:
        return None
```

- [ ] **Step 4: Ejecutar tests para verificar que pasan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_bot_api.py -v
```

Esperado: 6 tests PASS.

- [ ] **Step 5: Ejecutar todos los tests**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS (22 anteriores + 6 nuevos = 28).

- [ ] **Step 6: Commit**

```powershell
git -C C:\Users\octav\football-predictor add src/bot_api.py tests/test_bot_api.py
git -C C:\Users\octav\football-predictor commit -m "feat: add bot_api module for flask api calls"
```

---

### Task 3: Crear `src/bot_formatter.py` — formato de mensajes Telegram

**Files:**
- Create: `src/bot_formatter.py`
- Create: `tests/test_bot_formatter.py`

Este módulo convierte los dicts de la API en strings con formato Markdown de Telegram.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_bot_formatter.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot_formatter import format_fixtures_list, format_insight_message, format_no_fixtures

def _sample_fixtures():
    return [
        {"id": "1", "home_id": "42", "away_id": "99",
         "home_name": "River Plate", "away_name": "Boca Juniors",
         "date": "2025-06-03T21:00:00Z", "completed": False},
        {"id": "2", "home_id": "10", "away_id": "20",
         "home_name": "Racing", "away_name": "Independiente",
         "date": "2025-06-03T19:00:00Z", "completed": True},
    ]

def _sample_insight():
    return {
        "estilo_local": "River juega con posesión.",
        "estilo_visitante": "Boca presiona alto.",
        "desarrollo_partido": "Partido trabado en el medio.",
        "resultado_probable": "River 2-1 Boca",
        "corners": {"min": 8, "max": 11, "pick": 9.5},
        "amarillas": {"min": 3, "max": 5, "pick": 4.0},
        "parlay": {"picks": ["River gana", "Más de 9.5 corners"], "razon": "River dominante."}
    }

def test_format_fixtures_list_contains_team_names():
    text = format_fixtures_list(_sample_fixtures(), "Liga Argentina")
    assert "River Plate" in text
    assert "Boca Juniors" in text
    assert "Liga Argentina" in text

def test_format_fixtures_list_shows_completed_indicator():
    text = format_fixtures_list(_sample_fixtures(), "Liga Argentina")
    assert "✅" in text or "⚪" in text or "🟢" in text

def test_format_insight_message_contains_key_sections():
    text = format_insight_message("River Plate", "Boca Juniors", "Liga Argentina", _sample_insight())
    assert "River Plate" in text
    assert "Boca Juniors" in text
    assert "River 2-1 Boca" in text
    assert "9.5" in text
    assert "River gana" in text
    assert "PARLAY" in text.upper()

def test_format_insight_message_handles_missing_parlay():
    insight = _sample_insight()
    insight["parlay"] = {}
    text = format_insight_message("River", "Boca", "Liga Argentina", insight)
    assert "River" in text  # No crash

def test_format_no_fixtures_returns_string():
    text = format_no_fixtures("Premier League")
    assert "Premier League" in text
    assert isinstance(text, str)
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_bot_formatter.py -v
```

Esperado: `ImportError: No module named 'bot_formatter'`

- [ ] **Step 3: Crear `src/bot_formatter.py`**

```python
from datetime import datetime, timezone, timedelta

ART = timezone(timedelta(hours=-3))  # America/Argentina/Buenos_Aires

def _format_time(date_str: str) -> str:
    """Convierte fecha ISO a hora local Argentina."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(ART)
        return dt.strftime("%H:%M")
    except Exception:
        return ""

def format_fixtures_list(fixtures: list, league: str) -> str:
    """Formatea lista de partidos como texto Markdown para Telegram."""
    if not fixtures:
        return format_no_fixtures(league)
    lines = [f"⚽ *Partidos — {league}*\n"]
    for f in fixtures:
        time_str = _format_time(f.get("date", ""))
        icon = "✅" if f.get("completed") else "🟢"
        time_part = f" — {time_str}" if time_str else ""
        lines.append(f"{icon} {f['home_name']} vs {f['away_name']}{time_part}")
    return "\n".join(lines)

def format_insight_message(home_name: str, away_name: str, league: str, insight: dict) -> str:
    """Formatea análisis táctico + parlay como texto Markdown para Telegram."""
    corners = insight.get("corners", {})
    amarillas = insight.get("amarillas", {})
    parlay = insight.get("parlay", {})
    picks = parlay.get("picks", [])
    picks_text = "\n".join(f"✅ {p}" for p in picks) if picks else "Sin picks disponibles"

    return (
        f"🧠 *ANÁLISIS TÁCTICO*\n"
        f"*{home_name} vs {away_name}*\n"
        f"🏆 {league}\n\n"
        f"*Estilo {home_name}:* {insight.get('estilo_local', '—')}\n"
        f"*Estilo {away_name}:* {insight.get('estilo_visitante', '—')}\n\n"
        f"*Desarrollo esperado:* {insight.get('desarrollo_partido', '—')}\n\n"
        f"📊 *Resultado probable:* {insight.get('resultado_probable', '—')}\n"
        f"⚽ *Corners:* +{corners.get('pick', '—')} "
        f"(rango {corners.get('min', '—')}–{corners.get('max', '—')})\n"
        f"🟨 *Amarillas:* +{amarillas.get('pick', '—')} "
        f"(rango {amarillas.get('min', '—')}–{amarillas.get('max', '—')})\n\n"
        f"🎯 *PARLAY SUGERIDO*\n"
        f"{picks_text}\n\n"
        f"_{parlay.get('razon', '')}_"
    )

def format_no_fixtures(league: str) -> str:
    """Mensaje cuando no hay partidos disponibles para una liga."""
    return f"📭 No hay partidos disponibles hoy para *{league}*."
```

- [ ] **Step 4: Ejecutar tests para verificar que pasan**

```powershell
cd C:\Users\octav\football-predictor
python -m pytest tests/test_bot_formatter.py -v
```

Esperado: 5 tests PASS.

- [ ] **Step 5: Ejecutar todos los tests**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS.

- [ ] **Step 6: Commit**

```powershell
git -C C:\Users\octav\football-predictor add src/bot_formatter.py tests/test_bot_formatter.py
git -C C:\Users\octav\football-predictor commit -m "feat: add bot_formatter module for telegram message formatting"
```

---

### Task 4: Crear `bot.py` — bot principal

**Files:**
- Create: `bot.py`

No hay tests unitarios para el bot principal (depende de la API de Telegram). Se verifica manualmente en el Step final.

- [ ] **Step 1: Crear `bot.py`**

Crear el archivo `bot.py` en la raíz del proyecto:

```python
import os, logging, asyncio
from datetime import time as dtime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import sys
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

def _fixture_callback(league: str, fixture: dict) -> str:
    """Genera el callback_data para un botón de partido."""
    slug = _league_slug(league)
    parts = [
        "partido", league,
        str(fixture["home_id"]), str(fixture["away_id"]),
        fixture["home_name"], fixture["away_name"],
        slug, slug,
    ]
    return "|".join(parts)


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
    keyboard = []
    row = []
    for i, liga in enumerate(LIGAS):
        row.append(InlineKeyboardButton(liga, callback_data=f"liga|{liga}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text(
        "¿Qué liga querés ver?",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
    keyboard = []
    row = []
    for i, liga in enumerate(LIGAS):
        row.append(InlineKeyboardButton(liga, callback_data=f"liga|{liga}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await query.edit_message_text(
        "¿Qué liga querés ver?",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
        lambda: asyncio.ensure_future(publicar_partidos_del_dia(app.bot)),
        CronTrigger(hour=9, minute=0),
        id="publicar_9am",
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(publicar_partidos_del_dia(app.bot)),
        CronTrigger(hour=12, minute=0),
        id="publicar_12pm",
    )
    scheduler.start()

    logger.info("Bot iniciado. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verificar que el archivo no tiene errores de sintaxis**

```powershell
cd C:\Users\octav\football-predictor
python -c "import ast; ast.parse(open('bot.py').read()); print('OK')"
```

Esperado: `OK`

- [ ] **Step 3: Ejecutar todos los tests para confirmar que nada se rompió**

```powershell
python -m pytest tests/ -v
```

Esperado: todos los tests PASS.

- [ ] **Step 4: Commit**

```powershell
git -C C:\Users\octav\football-predictor add bot.py
git -C C:\Users\octav\football-predictor commit -m "feat: add telegram bot with scheduler and inline keyboard"
```

---

### Task 5: Verificación manual del bot

**Files:** ninguno

- [ ] **Step 1: Configurar el token real en `.env`**

Asegurarse de que `.env` tiene los valores reales:
```
TELEGRAM_BOT_TOKEN=<token de @BotFather>
TELEGRAM_CHANNEL_ID=<@username o ID numérico del canal>
FLASK_API_URL=http://localhost:5000
```

Para obtener el ID numérico del canal: agregá @userinfobot al canal, mandá un mensaje, te va a decir el ID.

- [ ] **Step 2: Asegurarse de que el Flask app está corriendo**

```powershell
cd C:\Users\octav\football-predictor
python src/app.py
```

En otra terminal:

- [ ] **Step 3: Iniciar el bot**

```powershell
cd C:\Users\octav\football-predictor
python bot.py
```

Esperado: `Bot iniciado. Polling...`

- [ ] **Step 4: Probar el bot privado**

En Telegram, buscar el bot por su username y mandar `/partidos`. Verificar:
- Aparece el teclado de ligas
- Tocar "Liga Argentina" → aparece lista de partidos
- Tocar un partido → aparece "⏳ Generando análisis..." → aparece el análisis completo con parlay

- [ ] **Step 5: Probar la publicación manual en el canal**

Desde una terminal Python, testear la publicación:

```powershell
cd C:\Users\octav\football-predictor
python -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from telegram import Bot
import sys; sys.path.insert(0, 'src')
from bot_api import get_fixtures
from bot_formatter import format_fixtures_list

async def test():
    bot = Bot(os.environ['TELEGRAM_BOT_TOKEN'])
    fixtures = get_fixtures('Liga Argentina')
    text = format_fixtures_list(fixtures, 'Liga Argentina')
    await bot.send_message(chat_id=os.environ['TELEGRAM_CHANNEL_ID'], text=text, parse_mode='Markdown')
    print('Mensaje enviado al canal')

asyncio.run(test())
"
```

Esperado: mensaje con la lista de partidos aparece en el canal.

- [ ] **Step 6: Commit y push**

```powershell
git -C C:\Users\octav\football-predictor add requirements.txt .env
git -C C:\Users\octav\football-predictor commit -m "chore: finalize bot setup and verification"
git -C C:\Users\octav\football-predictor push
```

Nota: `.env` NO debe commitearse. Solo `requirements.txt` si cambió.

```powershell
git -C C:\Users\octav\football-predictor add requirements.txt
git -C C:\Users\octav\football-predictor commit -m "chore: finalize telegram bot setup"
git -C C:\Users\octav\football-predictor push
```

---

### Task 6: Deploy en Railway

**Files:** ninguno — solo configuración en Railway

- [ ] **Step 1: Agregar variables de entorno en Railway**

En railway.app → tu proyecto → pestaña **Variables**, agregar:
- `TELEGRAM_BOT_TOKEN` = token de @BotFather
- `TELEGRAM_CHANNEL_ID` = ID del canal

`FLASK_API_URL` en Railway debe apuntar a la URL pública del web service, ej:
- `FLASK_API_URL=https://football-predictor.up.railway.app`

- [ ] **Step 2: Verificar que el Procfile tiene ambos procesos**

```
web: python src/app.py
bot: python bot.py
```

- [ ] **Step 3: Push y verificar deploy**

```powershell
git -C C:\Users\octav\football-predictor push
```

En Railway, verificar que ambos procesos (`web` y `bot`) aparecen y están corriendo en verde.

- [ ] **Step 4: Probar el bot en producción**

Mandar `/partidos` al bot en Telegram y verificar que responde con datos reales.
