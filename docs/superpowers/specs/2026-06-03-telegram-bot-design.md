# Telegram Bot — Diseño

**Fecha:** 2026-06-03
**Proyecto:** football-predictor
**Feature:** Bot de Telegram con canal automático + bot privado para análisis táctico y parlay sugerido

---

## Objetivo

Exponer el predictor de fútbol a usuarios de Telegram mediante:
1. Un **canal** donde se publican automáticamente partidos del día + análisis de los más importantes
2. Un **bot privado** donde los usuarios consultan partidos y piden análisis bajo demanda

---

## Arquitectura

```
Telegram Canal  ←── bot.py (APScheduler: 9AM + 12PM ART)
Telegram Bot    ←── bot.py (polling)
  (privado)              │
                    Flask API (Railway)
                    ├── GET /api/next-fixtures?league=...
                    ├── GET /api/analyze
                    └── POST /api/match-insight
```

`bot.py` es un proceso independiente que corre junto al Flask web en Railway:

```
# Procfile
web: python src/app.py
bot: python bot.py
```

---

## Archivos nuevos/modificados

| Archivo | Cambio |
|---|---|
| `bot.py` | **Nuevo** — bot principal: handlers, scheduler, formateo de mensajes |
| `Procfile` | Agregar proceso `bot:` |
| `requirements.txt` | Agregar `python-telegram-bot[job-queue]`, `APScheduler` |
| `.env` | Agregar `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `FLASK_API_URL` |

---

## Variables de entorno

| Variable | Descripción |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot obtenido de @BotFather |
| `TELEGRAM_CHANNEL_ID` | ID del canal (ej: `@mi_canal` o `-100123456789`) |
| `FLASK_API_URL` | URL base de la API Flask (ej: `https://football-predictor.railway.app`) |

---

## Bot privado — Flujo de usuario

### Comando `/partidos`

1. Bot responde con teclado inline de ligas:
   ```
   ¿Qué liga?
   [Premier League] [La Liga] [Serie A]
   [Champions League] [Liga Argentina] [Más ligas...]
   ```

2. Usuario toca una liga → bot llama `GET /api/next-fixtures?league=<liga>` y muestra lista de partidos como botones:
   ```
   ⚽ Partidos — Liga Argentina
   🟢 River Plate vs Boca Juniors — 21:00
   ⚪ Racing vs Independiente — 19:00
   ```

3. Usuario toca un partido → bot muestra "⏳ Generando análisis..." y llama:
   - `GET /api/analyze` con los parámetros del partido
   - `POST /api/match-insight` con los datos del análisis

4. Bot responde con el análisis formateado (ver formato de mensaje abajo)

### Callback data format

`partido|{league}|{home_id}|{away_id}|{home_name}|{away_name}|{home_slug}|{away_slug}`

Ejemplo: `partido|Liga Argentina|42|99|River Plate|Boca Juniors|arg.1|arg.1`

---

## Canal — Publicación automática

**Horario:** 9:00 AM y 12:00 PM hora Argentina (UTC-3), usando `APScheduler` con timezone `America/Argentina/Buenos_Aires`

**Ligas publicadas automáticamente:**
- Premier League
- La Liga
- Champions League
- Liga Argentina
- Brasileirao

**Por cada liga:**
1. Llama `GET /api/next-fixtures?league=<liga>`
2. Si hay partidos: publica la lista completa
3. Analiza los primeros 3 partidos (los más relevantes según ESPN) llamando `/api/analyze` + `/api/match-insight` para cada uno
4. Publica cada análisis como mensaje separado en el canal

Si una liga no tiene partidos ese día, se omite silenciosamente.

---

## Formato de mensaje — Análisis táctico

```
🧠 *ANÁLISIS TÁCTICO*
*River Plate vs Boca Juniors*
🏆 Liga Argentina

*Estilo River:* Juego de posesión con salida limpia...
*Estilo Boca:* Presión alta y transiciones rápidas...

*Desarrollo esperado:* Se anticipa un partido trabado...

📊 *Resultado probable:* River 2-1 Boca
⚽ *Corners:* +9.5 (rango 8–11)
🟨 *Amarillas:* +4 (rango 3–5)

🎯 *PARLAY SUGERIDO*
✅ River gana
✅ Más de 9.5 corners

_River es favorito en casa con 3 victorias consecutivas..._
```

Usa formato Markdown de Telegram (`parse_mode=Markdown`).

---

## Manejo de errores

- Si `/api/next-fixtures` falla → el scheduler omite esa liga, no crashea
- Si `/api/analyze` o `/api/match-insight` falla → el bot responde "⚠️ No se pudo generar el análisis para este partido"
- Si Claude API no está disponible → el bot muestra el análisis estadístico básico sin la sección táctica
- Timeout de requests a la API Flask: 30 segundos

---

## Dependencias nuevas

```
python-telegram-bot[job-queue]>=21.0
APScheduler>=3.10
```

---

## Degradación graceful

- Bot privado y canal son independientes — si el scheduler falla, el bot privado sigue funcionando
- Si `TELEGRAM_CHANNEL_ID` no está configurado, el scheduler se desactiva sin error
- Si `FLASK_API_URL` no está configurado, el bot responde con error claro al usuario
