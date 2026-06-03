import requests

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
HEADERS = {"User-Agent": "Mozilla/5.0"}

LEAGUES = {
    "Premier League":    "eng.1",
    "La Liga":           "esp.1",
    "Serie A":           "ita.1",
    "Bundesliga":        "ger.1",
    "Ligue 1":           "fra.1",
    "Champions League":  "uefa.champions",
    "Europa League":     "uefa.europa",
    "Brasileirao":       "bra.1",
    "Liga Argentina":    "arg.1",
    "Copa Argentina":    "af:130",
    "Copa Libertadores": "conmebol.libertadores",
    "Copa Sudamericana": "conmebol.sudamericana",
    "Mundial":           "fifa.world",
    "Amistosos Internacionales": "fifa.friendly",
}

# Ligas europeas que compiten en Champions/Europa
EUROPEAN_LEAGUES = ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1"]
SOUTH_AMERICAN_LEAGUES = ["bra.1", "arg.1"]

def get(path, params=None):
    resp = requests.get(f"{BASE_URL}/{path}", headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_scoreboard(league_slug, limit=15):
    return get(f"{league_slug}/scoreboard", {"limit": limit})

def get_team_schedule(league_slug, team_id):
    return get(f"{league_slug}/teams/{team_id}/schedule")

def get_teams(league_slug):
    return get(f"{league_slug}/teams", {"limit": 100})

def get_summary(league_slug, event_id):
    return get(f"{league_slug}/summary", {"event": event_id})

def search_teams_across_leagues(query):
    results = []
    seen_ids = set()
    query_lower = query.lower()
    for league_name, slug in LEAGUES.items():
        try:
            data = get_teams(slug)
            for team in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
                t = team.get("team", {})
                if query_lower in t.get("displayName", "").lower() or query_lower in t.get("name", "").lower():
                    tid = t.get("id")
                    if tid not in seen_ids:
                        seen_ids.add(tid)
                        results.append({
                            "id": tid,
                            "name": t.get("displayName", t.get("name")),
                            "logo": t.get("logos", [{}])[0].get("href", ""),
                            "league": league_name,
                            "league_slug": slug,
                        })
        except Exception:
            continue
    return results


UNAVAILABLE_STATUSES = {"Out", "Doubtful", "Suspended"}

def get_team_injuries(team_id, league_slug):
    """Returns list of player names that are Out, Doubtful, or Suspended."""
    try:
        data = get(f"{league_slug}/injuries")
        injured = []
        for entry in data.get("injuries", []):
            if entry.get("team", {}).get("id") != str(team_id):
                continue
            for injury in entry.get("injuries", []):
                status = injury.get("status", "")
                if status not in UNAVAILABLE_STATUSES:
                    continue
                name = injury.get("athlete", {}).get("displayName", "")
                if name:
                    injured.append(name)
        return injured
    except Exception:
        return []
