import os, json, re
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"

def build_prompt(home_name, away_name, home_form, away_form, h2h, home_injured, away_injured, alerts):
    def fmt_form(name, form, injured):
        top_scorers = ", ".join(f"{p['name']} ({p['goals']} goles)" for p in form.get("top_scorers", [])[:3]) or "Sin datos"
        top_assists = ", ".join(f"{p['name']} ({p['assists']} asist.)" for p in form.get("top_assists", [])[:3]) or "Sin datos"
        injured_str = ", ".join(injured) if injured else "Ninguno conocido"
        return f"""
## {name}
- Forma reciente: {form.get("form", "N/D")}
- Goles a favor/contra por partido: {form.get("avg_goals_for")}/{form.get("avg_goals_against")}
- Posesión promedio: {form.get("avg_possession")}%
- Tiros/partido: {form.get("avg_shots")} (al arco: {form.get("avg_shots_on")})
- Faltas/partido: {form.get("avg_fouls")}
- Corners/partido: {form.get("avg_corners")}
- Tarjetas amarillas/partido: {form.get("avg_yellow_cards")}
- Goleadores: {top_scorers}
- Asistidores: {top_assists}
- Lesionados/suspendidos: {injured_str}"""

    h2h_str = f"Últimos {h2h.get('total', 0)} enfrentamientos: {home_name} ganó {h2h.get('home_wins', 0)}, empates {h2h.get('draws', 0)}, {away_name} ganó {h2h.get('away_wins', 0)}" if h2h.get("total", 0) > 0 else "Sin historial H2H disponible"
    alerts_str = "\n".join(f"- {a}" for a in alerts) if alerts else "Ninguna"

    return f"""Eres un analista de fútbol experto. Analiza este partido y responde ÚNICAMENTE con un JSON válido, sin texto adicional.

# Partido: {home_name} (local) vs {away_name} (visitante)

{fmt_form(home_name, home_form, home_injured)}
{fmt_form(away_name, away_form, away_injured)}

## Historial directo (H2H)
{h2h_str}

## Alertas
{alerts_str}

# Instrucciones
Basándote en los datos anteriores, devuelve este JSON exacto:
{{
  "estilo_local": "<2-3 oraciones sobre el estilo de juego del equipo local>",
  "estilo_visitante": "<2-3 oraciones sobre el estilo de juego del visitante>",
  "desarrollo_partido": "<3-4 oraciones describiendo cómo se espera que se desarrolle el encuentro>",
  "resultado_probable": "<ej: {home_name} 2-1 {away_name}>",
  "corners": {{"min": <entero>, "max": <entero>, "pick": <número con .5>}},
  "amarillas": {{"min": <entero>, "max": <entero>, "pick": <número con .5>}},
  "parlay": {{
    "picks": ["<pick 1>", "<pick 2>"],
    "razon": "<2-3 oraciones justificando la combinada>"
  }}
}}

Para el parlay, sé conservador: elegí picks de alta probabilidad (equivalente a cuotas implícitas 1.20–1.50), preferí mercados simples (resultado 1X2 u over/under goles totales), usá máximo 2 picks en la combinada, y evitá combinar eventos correlacionados. Justificá brevemente por qué cada pick tiene alta probabilidad de ocurrir."""


def generate_insight(prompt):
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return {"error": "Variable ANTHROPIC_API_KEY no encontrada en el servidor. Verificá que esté configurada en Railway con ese nombre exacto."}
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        # Limpiar posibles bloques de código markdown
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


def get_match_insight(home_name, away_name, home_form, away_form, h2h, home_injured, away_injured, alerts):
    prompt = build_prompt(home_name, away_name, home_form, away_form, h2h, home_injured, away_injured, alerts)
    return generate_insight(prompt)
