import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import patch, MagicMock
from api_football_client import find_team_id, convert_to_espn_format, get_team_events

def _mock_teams_response(team_id="42", name="River Plate"):
    return {
        "response": [
            {"team": {"id": team_id, "name": name}}
        ]
    }

def _mock_fixtures_response():
    return {
        "response": [
            {
                "fixture": {
                    "id": 999,
                    "date": "2025-05-10T20:00:00+00:00",
                    "status": {"short": "FT"}
                },
                "teams": {
                    "home": {"id": 42, "name": "River Plate", "winner": True},
                    "away": {"id": 99, "name": "Boca Juniors", "winner": False}
                },
                "goals": {"home": 2, "away": 1}
            }
        ]
    }

def _mock_stats_response(team_id="42"):
    return {
        "response": [
            {
                "team": {"id": int(team_id)},
                "statistics": [
                    {"type": "Corner Kicks", "value": 6},
                    {"type": "Yellow Cards", "value": 2},
                    {"type": "Total Shots", "value": 14},
                    {"type": "Shots on Goal", "value": 5},
                    {"type": "Fouls", "value": 11},
                    {"type": "Ball Possession", "value": "54%"},
                ]
            }
        ]
    }

def test_find_team_id_returns_id():
    with patch('api_football_client._get', return_value=_mock_teams_response("42")):
        result = find_team_id("River Plate", 130)
    assert result == "42"

def test_find_team_id_returns_none_when_no_results():
    with patch('api_football_client._get', return_value={"response": []}):
        result = find_team_id("Equipo Inexistente", 130)
    assert result is None

def test_find_team_id_returns_none_on_exception():
    with patch('api_football_client._get', side_effect=Exception("Network error")):
        result = find_team_id("River Plate", 130)
    assert result is None

def test_convert_to_espn_format_structure():
    fixtures = _mock_fixtures_response()["response"]
    with patch('api_football_client._get', return_value=_mock_stats_response("42")):
        events = convert_to_espn_format(fixtures, "42", "af:130")
    assert len(events) == 1
    e = events[0]
    assert e["id"] == "af_999"
    assert e["_league_slug"] == "af:130"
    assert e["_source"] == "api_football"
    comp = e["competitions"][0]
    assert comp["status"]["type"]["completed"] is True
    competitors = comp["competitors"]
    home = next(c for c in competitors if c["homeAway"] == "home")
    assert home["team"]["id"] == "42"
    assert home["score"] == "2"
    assert home["winner"] is True

def test_convert_to_espn_format_includes_stats():
    fixtures = _mock_fixtures_response()["response"]
    with patch('api_football_client._get', return_value=_mock_stats_response("42")):
        events = convert_to_espn_format(fixtures, "42", "af:130")
    stats = events[0]["competitions"][0]["_stats"]
    assert stats["cornersKicked"] == 6
    assert stats["yellowCards"] == 2
    assert stats["possessionPct"] == 54.0

def test_get_team_events_returns_empty_on_exception():
    with patch('api_football_client._get', side_effect=Exception("API down")):
        result = get_team_events("River Plate", "af:130")
    assert result == []
