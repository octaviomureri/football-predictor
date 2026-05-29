import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify
from api_client import get_scoreboard, get_teams, search_teams_across_leagues, LEAGUES
from analyzer import analyze_match

app = Flask(__name__, template_folder="../templates")

@app.route("/")
def index():
    return render_template("index.html", leagues=list(LEAGUES.keys()))

@app.route("/api/next-fixtures")
def next_fixtures():
    league_name = request.args.get("league", "Premier League")
    slug = LEAGUES[league_name]
    try:
        data = get_scoreboard(slug, limit=15)
        events = data.get("events", [])
        result = []
        for e in events:
            comp = e.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            home = next((c for c in competitors if c["homeAway"] == "home"), None)
            away = next((c for c in competitors if c["homeAway"] == "away"), None)
            if not home or not away:
                continue
            status = comp.get("status", {}).get("type", {})
            result.append({
                "id": e["id"],
                "home_id": home["team"]["id"],
                "home_name": home["team"]["displayName"],
                "home_logo": home["team"].get("logo", ""),
                "away_id": away["team"]["id"],
                "away_name": away["team"]["displayName"],
                "away_logo": away["team"].get("logo", ""),
                "date": e.get("date", ""),
                "status": status.get("description", ""),
                "completed": status.get("completed", False),
            })
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/search-team")
def search():
    query = request.args.get("q", "")
    if len(query) < 2:
        return jsonify([])
    try:
        teams = search_teams_across_leagues(query)
        return jsonify(teams[:10])
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

@app.route("/api/analyze")
def analyze():
    league_name = request.args.get("league")
    home_id = request.args.get("home_id")
    away_id = request.args.get("away_id")
    home_name = request.args.get("home_name", "Local")
    away_name = request.args.get("away_name", "Visitante")
    raw_slug = request.args.get("league_slug", "")
    # Si el slug contiene espacios o mayúsculas es un nombre, no un slug real
    league_slug = raw_slug if (raw_slug and "." in raw_slug) else LEAGUES.get(league_name, "eng.1")

    try:
        result = analyze_match(league_slug, home_id, away_id, home_name, away_name)
        return jsonify(result)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
