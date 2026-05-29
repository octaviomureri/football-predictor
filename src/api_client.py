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
    "Copa Libertadores": "conmebol.libertadores",
    "Copa Sudamericana": "conmebol.sudamericana",
    "Mundial":           "fifa.world",
}

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

def get_roster(league_slug, team_id):
    return get(f"{league_slug}/teams/{team_id}/roster")

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
