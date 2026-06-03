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
