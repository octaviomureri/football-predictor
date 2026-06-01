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
