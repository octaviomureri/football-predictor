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
