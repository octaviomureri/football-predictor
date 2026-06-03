from api_client import get_team_schedule, get_summary, LEAGUES, EUROPEAN_LEAGUES, SOUTH_AMERICAN_LEAGUES

def safe(val, default=0):
    return val if val is not None else default

def parse_score(s):
    if isinstance(s, dict):
        try:
            return int(safe(s.get("value", s.get("displayValue", 0))) or 0)
        except (ValueError, TypeError):
            return 0
    try:
        return int(safe(s) or 0)
    except (ValueError, TypeError):
        return 0

def extract_player_stats_from_summary(summary, team_id):
    """Extrae goles, asistencias desde keyEvents y tarjetas desde rosters."""
    goals = {}
    assists = {}
    cards = {}

    # Goles y asistencias desde keyEvents
    for event in summary.get("keyEvents", []):
        team = event.get("team", {})
        if team.get("id") != str(team_id):
            continue
        event_type = event.get("type", {}).get("type", "")
        participants = event.get("participants", [])
        if not participants:
            continue
        first = participants[0].get("athlete", {}).get("displayName", "")
        if event.get("scoringPlay") and event_type != "ownGoal":
            if first:
                goals[first] = goals.get(first, 0) + 1
            if len(participants) > 1:
                assister = participants[1].get("athlete", {}).get("displayName", "")
                if assister and assister != first:
                    assists[assister] = assists.get(assister, 0) + 1

    # Tarjetas desde rosters (plays por jugador)
    for team_roster in summary.get("rosters", []):
        if team_roster.get("team", {}).get("id") != str(team_id):
            continue
        for player in team_roster.get("roster", []):
            name = player.get("athlete", {}).get("displayName", "")
            if not name:
                continue
            yellows = sum(1 for p in player.get("plays", []) if p.get("yellowCard"))
            reds = sum(1 for p in player.get("plays", []) if p.get("redCard"))
            if yellows or reds:
                if name not in cards:
                    cards[name] = {"yellow": 0, "red": 0}
                cards[name]["yellow"] += yellows
                cards[name]["red"] += reds

    return goals, assists, cards

def extract_team_stats_from_summary(summary, team_id):
    """Extrae posesión, tiros, faltas de boxscore.teams del summary."""
    stats = {}
    teams = summary.get("boxscore", {}).get("teams", [])
    for team_entry in teams:
        if team_entry.get("team", {}).get("id") != str(team_id):
            continue
        for stat in team_entry.get("statistics", []):
            name = stat.get("name", "")
            val = stat.get("displayValue", "0")
            try:
                stats[name] = float(val.replace("%", ""))
            except (ValueError, TypeError):
                pass
    return stats

def get_all_team_events(team_id, primary_slug, team_name=""):
    """Obtiene partidos del equipo en todas sus competiciones relevantes.
    Usa API-Football si el slug empieza con 'af:' o si ESPN devuelve menos de 5 partidos.
    """
    all_events = []
    seen_event_ids = set()

    # Slug af: → ir directo a API-Football
    if primary_slug.startswith("af:"):
        try:
            from api_football_client import get_team_events as af_get
            return af_get(team_name, primary_slug)
        except Exception:
            return []

    # Determinar ligas adicionales según la liga principal
    extra_slugs = []
    if primary_slug in EUROPEAN_LEAGUES:
        extra_slugs = ["uefa.champions", "uefa.europa"]
    elif primary_slug in SOUTH_AMERICAN_LEAGUES:
        extra_slugs = ["conmebol.libertadores", "conmebol.sudamericana"]

    slugs_to_check = [primary_slug] + extra_slugs

    for slug in slugs_to_check:
        try:
            data = get_team_schedule(slug, team_id)
            events = data.get("events", [])
            for e in events:
                if e["id"] not in seen_event_ids:
                    seen_event_ids.add(e["id"])
                    e["_league_slug"] = slug
                    all_events.append(e)
        except Exception:
            continue

    all_events.sort(key=lambda e: e.get("date", ""))

    # Fallback a API-Football si hay pocos datos de ESPN
    if len(all_events) < 5 and team_name:
        try:
            from api_football_client import get_team_events as af_get
            league_map = {
                "arg.1": "af:112", "bra.1": "af:71",
                "eng.1": "af:39", "esp.1": "af:140",
                "ita.1": "af:135", "ger.1": "af:78", "fra.1": "af:61",
            }
            af_slug = league_map.get(primary_slug)
            if af_slug:
                af_events = af_get(team_name, af_slug)
                for e in af_events:
                    if e["id"] not in seen_event_ids:
                        seen_event_ids.add(e["id"])
                        all_events.append(e)
                all_events.sort(key=lambda e: e.get("date", ""))
        except Exception:
            pass

    return all_events

def analyze_schedule(events, team_id, league_slug, last=10):
    results = []
    gf_list, ga_list = [], []
    shots_list, shots_on_list, fouls_list, possession_list = [], [], [], []
    corners_list, yellow_cards_list = [], []
    all_goals = {}
    all_assists = {}
    all_cards = {}

    finished = [
        e for e in events
        if e.get("competitions") and
           e["competitions"][0].get("status", {}).get("type", {}).get("completed", False)
    ]

    for e in finished[-last:]:
        league_slug = e.get("_league_slug", league_slug)
        comp = e["competitions"][0]
        home_comp = next((c for c in comp.get("competitors", []) if c["homeAway"] == "home"), None)
        away_comp = next((c for c in comp.get("competitors", []) if c["homeAway"] == "away"), None)
        if not home_comp or not away_comp:
            continue

        # API-Football events mark the target team with _is_target; ESPN events use team_id
        if home_comp.get("_is_target") or away_comp.get("_is_target"):
            is_home = bool(home_comp.get("_is_target"))
        else:
            is_home = home_comp["team"]["id"] == str(team_id)
        my = home_comp if is_home else away_comp
        opp = away_comp if is_home else home_comp

        gf = parse_score(my.get("score", 0))
        ga = parse_score(opp.get("score", 0))
        gf_list.append(gf)
        ga_list.append(ga)

        if my.get("winner"):
            results.append("W")
        elif opp.get("winner"):
            results.append("L")
        else:
            results.append("D")

        try:
            comp = e["competitions"][0]
            # Eventos de API-Football traen _stats directamente
            if "_stats" in comp:
                team_stats = comp["_stats"]
                summary = {}
            else:
                summary = get_summary(league_slug, e["id"])
                team_stats = extract_team_stats_from_summary(summary, team_id)

            if "totalShots" in team_stats:
                shots_list.append(team_stats["totalShots"])
            if "shotsOnTarget" in team_stats:
                shots_on_list.append(team_stats["shotsOnTarget"])
            if "foulsCommitted" in team_stats:
                fouls_list.append(team_stats["foulsCommitted"])
            if "possessionPct" in team_stats:
                possession_list.append(team_stats["possessionPct"])
            if "cornersKicked" in team_stats:
                corners_list.append(team_stats["cornersKicked"])
            if "yellowCards" in team_stats:
                yellow_cards_list.append(team_stats["yellowCards"])

            g, a, c = extract_player_stats_from_summary(summary, team_id)
            for name, val in g.items():
                all_goals[name] = all_goals.get(name, 0) + val
            for name, val in a.items():
                all_assists[name] = all_assists.get(name, 0) + val
            for name, val in c.items():
                if name not in all_cards:
                    all_cards[name] = {"yellow": 0, "red": 0}
                all_cards[name]["yellow"] += val["yellow"]
                all_cards[name]["red"] += val["red"]
        except Exception:
            pass

    matches = len(results)
    avg = lambda lst: round(sum(lst) / len(lst), 2) if lst else 0

    # Competiciones únicas analizadas
    competitions = list({e.get("_league_slug", "") for e in finished[-last:] if e.get("_league_slug")})

    return {
        "form": "".join(results[-5:]),
        "points": sum(3 if r == "W" else 1 if r == "D" else 0 for r in results),
        "avg_goals_for": avg(gf_list),
        "avg_goals_against": avg(ga_list),
        "avg_possession": avg(possession_list),
        "avg_shots": avg(shots_list),
        "avg_shots_on": avg(shots_on_list),
        "avg_fouls": avg(fouls_list),
        "avg_corners": avg(corners_list),
        "avg_yellow_cards": avg(yellow_cards_list),
        "matches_analyzed": matches,
        "competitions_count": len(competitions),
        "top_scorers": [{"name": n, "goals": g} for n, g in sorted(all_goals.items(), key=lambda x: -x[1])[:5]],
        "top_assists": [{"name": n, "assists": a} for n, a in sorted(all_assists.items(), key=lambda x: -x[1])[:5]],
        "top_cards": [{"name": n, "yellow": v["yellow"], "red": v["red"]}
                      for n, v in sorted(all_cards.items(), key=lambda x: -(x[1]["yellow"] + x[1]["red"] * 3))[:5]],
    }

def analyze_h2h(home_events, home_team_id, away_team_id):
    h2h = []
    for e in home_events:
        if not e.get("competitions"):
            continue
        comp = e["competitions"][0]
        team_ids = {c["team"]["id"] for c in comp.get("competitors", [])}
        if str(away_team_id) in team_ids and comp.get("status", {}).get("type", {}).get("completed"):
            h2h.append(comp)

    hw = aw = d = 0
    for comp in h2h[-6:]:
        home_c = next((c for c in comp["competitors"] if c["homeAway"] == "home"), None)
        away_c = next((c for c in comp["competitors"] if c["homeAway"] == "away"), None)
        if not home_c or not away_c:
            continue
        is_home_local = home_c["team"]["id"] == str(home_team_id)
        if home_c.get("winner"):
            hw += 1 if is_home_local else 0
            aw += 0 if is_home_local else 1
        elif away_c.get("winner"):
            aw += 1 if is_home_local else 0
            hw += 0 if is_home_local else 1
        else:
            d += 1

    return {"home_wins": hw, "away_wins": aw, "draws": d, "total": len(h2h[-6:])}

def predict_result(home_form, away_form):
    ha = home_form["avg_goals_for"]
    hd = 1 / (home_form["avg_goals_against"] + 0.5)
    aa = away_form["avg_goals_for"]
    ad = 1 / (away_form["avg_goals_against"] + 0.5)

    home_xg = max(0.3, ha * ad * 1.25)
    away_xg = max(0.3, aa * hd)
    raw_draw = (home_xg + away_xg) * 0.38
    total = home_xg + raw_draw + away_xg

    prob_home = round(home_xg / total * 100, 1)
    prob_draw = round(raw_draw / total * 100, 1)
    prob_away = round(away_xg / total * 100, 1)
    btts = round((1 - 1/(home_xg+1)) * (1 - 1/(away_xg+1)) * 100, 1)

    best = max([("Local", prob_home), ("Empate", prob_draw), ("Visitante", prob_away)], key=lambda x: x[1])
    return {
        "prob_home": prob_home, "prob_draw": prob_draw, "prob_away": prob_away,
        "btts_prob": btts, "best_bet": best[0], "confidence": best[1],
        "home_expected_goals": round(home_xg, 2), "away_expected_goals": round(away_xg, 2),
    }

def get_mood_alerts(home_form, away_form, home_name, away_name):
    alerts = []
    for name, form in [(home_name, home_form), (away_name, away_form)]:
        f = form["form"]
        if f.endswith("LLL"):
            alerts.append(f"🔴 {name} viene de 3 derrotas consecutivas — moral baja")
        elif f.count("L") >= 3:
            alerts.append(f"⚠️ {name} perdió {f.count('L')} de los últimos {len(f)} partidos")
        if f.endswith("WWW"):
            alerts.append(f"🟢 {name} viene de 3 victorias seguidas — en gran momento")
        if form["avg_goals_against"] > 2.2:
            alerts.append(f"⚠️ {name} recibe muchos goles ({form['avg_goals_against']}/partido)")
        if form["matches_analyzed"] < 3:
            alerts.append(f"ℹ️ {name}: pocos partidos disponibles ({form['matches_analyzed']})")
    return alerts

def analyze_match(home_slug, away_slug, home_team_id, away_team_id, home_name="Local", away_name="Visitante"):
    home_events = get_all_team_events(home_team_id, home_slug, team_name=home_name)
    away_events = get_all_team_events(away_team_id, away_slug, team_name=away_name)

    home_form = analyze_schedule(home_events, home_team_id, home_slug)
    away_form = analyze_schedule(away_events, away_team_id, away_slug)
    h2h = analyze_h2h(home_events, home_team_id, away_team_id)
    prediction = predict_result(home_form, away_form)
    alerts = get_mood_alerts(home_form, away_form, home_name, away_name)

    return {
        "prediction": prediction,
        "home_form": home_form,
        "away_form": away_form,
        "h2h": h2h,
        "mood_alerts": alerts,
    }
