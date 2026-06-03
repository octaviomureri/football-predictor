from unittest.mock import patch
from analyzer import analyze_schedule

def _make_event(event_id, team_id, gf, ga, winner_home=True):
    """Helper que construye un evento ESPN mínimo ya completado."""
    my_id = str(team_id)
    opp_id = "999"
    return {
        "id": event_id,
        "date": "2024-01-01T00:00:00Z",
        "_league_slug": "eng.1",
        "competitions": [{
            "status": {"type": {"completed": True}},
            "competitors": [
                {"homeAway": "home", "team": {"id": my_id}, "score": str(gf), "winner": winner_home},
                {"homeAway": "away", "team": {"id": opp_id}, "score": str(ga), "winner": not winner_home},
            ]
        }]
    }

def _mock_summary_with_stats(corners=5, yellow_cards=2):
    return {
        "keyEvents": [],
        "rosters": [],
        "boxscore": {
            "teams": [{
                "team": {"id": "42"},
                "statistics": [
                    {"name": "cornersKicked", "displayValue": str(corners)},
                    {"name": "yellowCards", "displayValue": str(yellow_cards)},
                    {"name": "possessionPct", "displayValue": "55"},
                    {"name": "totalShots", "displayValue": "12"},
                    {"name": "shotsOnTarget", "displayValue": "5"},
                    {"name": "foulsCommitted", "displayValue": "8"},
                ]
            }]
        }
    }

def test_analyze_schedule_includes_avg_corners_and_yellow_cards():
    events = [_make_event("e1", 42, 2, 0), _make_event("e2", 42, 1, 1, winner_home=False)]
    with patch('analyzer.get_summary', return_value=_mock_summary_with_stats(corners=6, yellow_cards=3)):
        result = analyze_schedule(events, 42, "eng.1")
    assert "avg_corners" in result
    assert "avg_yellow_cards" in result
    assert result["avg_corners"] == 6.0
    assert result["avg_yellow_cards"] == 3.0

def test_analyze_schedule_avg_corners_zero_when_no_data():
    events = [_make_event("e1", 42, 2, 0)]
    with patch('analyzer.get_summary', return_value={"keyEvents": [], "rosters": [], "boxscore": {"teams": []}}):
        result = analyze_schedule(events, 42, "eng.1")
    assert result["avg_corners"] == 0
    assert result["avg_yellow_cards"] == 0

def test_get_all_team_events_uses_api_football_for_af_slug():
    from unittest.mock import patch
    from analyzer import get_all_team_events

    af_events = [
        {
            "id": "af_999",
            "date": "2025-05-10T20:00:00Z",
            "_league_slug": "af:130",
            "_source": "api_football",
            "competitions": [{
                "status": {"type": {"completed": True}},
                "_stats": {},
                "competitors": [
                    {"homeAway": "home", "team": {"id": "42"}, "score": "2", "winner": True},
                    {"homeAway": "away", "team": {"id": "99"}, "score": "1", "winner": False},
                ]
            }]
        }
    ]

    with patch('api_football_client.get_team_events', return_value=af_events):
        result = get_all_team_events("42", "af:130", team_name="River Plate")

    assert len(result) == 1
    assert result[0]["_source"] == "api_football"

def test_get_all_team_events_fallback_when_espn_insufficient():
    from unittest.mock import patch, MagicMock
    from analyzer import get_all_team_events

    # ESPN devuelve solo 2 partidos (< 5)
    espn_event = {
        "id": "esp_1",
        "date": "2025-04-01T00:00:00Z",
        "_league_slug": "arg.1",
        "competitions": [{"status": {"type": {"completed": True}}, "competitors": [
            {"homeAway": "home", "team": {"id": "42"}, "score": "1", "winner": True},
            {"homeAway": "away", "team": {"id": "99"}, "score": "0", "winner": False},
        ]}]
    }
    af_event = {
        "id": "af_999",
        "date": "2025-05-01T00:00:00Z",
        "_league_slug": "arg.1",
        "_source": "api_football",
        "competitions": [{"status": {"type": {"completed": True}}, "_stats": {}, "competitors": [
            {"homeAway": "home", "team": {"id": "42"}, "score": "2", "winner": True},
            {"homeAway": "away", "team": {"id": "99"}, "score": "1", "winner": False},
        ]}]
    }

    mock_schedule = MagicMock()
    mock_schedule.return_value = {"events": [espn_event, espn_event]}  # solo 2

    with patch('api_client.get_team_schedule', mock_schedule), \
         patch('api_football_client.get_team_events', return_value=[af_event]):
        result = get_all_team_events("42", "arg.1", team_name="River Plate")

    ids = [e["id"] for e in result]
    assert "af_999" in ids
