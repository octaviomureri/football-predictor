import os, requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"
CURRENT_SEASON = 2025

def _headers():
    return {
        "X-RapidAPI-Key": os.environ.get("API_FOOTBALL_KEY", ""),
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
    }

def _get(path, params=None):
    resp = requests.get(f"{BASE_URL}/{path}", headers=_headers(), params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def find_team_id(team_name, league_id):
    """Busca el team_id de API-Football por nombre y liga. Retorna str o None."""
    try:
        data = _get("teams", {"name": team_name, "league": league_id, "season": CURRENT_SEASON})
        results = data.get("response", [])
        if not results:
            return None
        return str(results[0]["team"]["id"])
    except Exception:
        return None

def _get_fixture_stats(fixture_id, af_team_id):
    """Retorna dict de stats del equipo en el fixture, o {} si falla."""
    try:
        data = _get("fixtures/statistics", {"fixture": fixture_id, "team": af_team_id})
        for entry in data.get("response", []):
            if str(entry["team"]["id"]) != str(af_team_id):
                continue
            stats = {}
            mapping = {
                "Corner Kicks": "cornersKicked",
                "Yellow Cards": "yellowCards",
                "Total Shots": "totalShots",
                "Shots on Goal": "shotsOnTarget",
                "Fouls": "foulsCommitted",
                "Ball Possession": "possessionPct",
            }
            for s in entry.get("statistics", []):
                key = mapping.get(s["type"])
                if not key:
                    continue
                val = s["value"]
                if val is None:
                    continue
                if isinstance(val, str) and val.endswith("%"):
                    val = float(val.replace("%", ""))
                try:
                    stats[key] = float(val)
                except (ValueError, TypeError):
                    pass
            return stats
        return {}
    except Exception:
        return {}

def convert_to_espn_format(fixtures, af_team_id, league_slug):
    """Convierte lista de fixtures de API-Football al formato de eventos ESPN-compatible."""
    events = []
    for f in fixtures:
        fixture_info = f.get("fixture", {})
        fixture_id = fixture_info.get("id")
        status_short = fixture_info.get("status", {}).get("short", "")
        completed = status_short in ("FT", "AET", "PEN")

        teams = f.get("teams", {})
        goals = f.get("goals", {})
        home_team = teams.get("home", {})
        away_team = teams.get("away", {})

        stats = {}
        if completed and fixture_id:
            stats = _get_fixture_stats(fixture_id, af_team_id)

        events.append({
            "id": f"af_{fixture_id}",
            "date": fixture_info.get("date", ""),
            "_league_slug": league_slug,
            "_source": "api_football",
            "competitions": [{
                "status": {"type": {"completed": completed}},
                "_stats": stats,
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {"id": str(home_team.get("id", ""))},
                        "score": str(goals.get("home") or 0),
                        "winner": bool(home_team.get("winner")),
                    },
                    {
                        "homeAway": "away",
                        "team": {"id": str(away_team.get("id", ""))},
                        "score": str(goals.get("away") or 0),
                        "winner": bool(away_team.get("winner")),
                    },
                ],
            }],
        })
    return events

def get_team_events(team_name, league_slug):
    """Obtiene partidos de un equipo desde API-Football. Retorna [] ante cualquier error."""
    try:
        league_id = int(league_slug.split(":")[1])
        af_team_id = find_team_id(team_name, league_id)
        if not af_team_id:
            return []
        data = _get("fixtures", {
            "team": af_team_id,
            "league": league_id,
            "season": CURRENT_SEASON,
            "last": 15,
        })
        fixtures = data.get("response", [])
        return convert_to_espn_format(fixtures, af_team_id, league_slug)
    except Exception:
        return []
