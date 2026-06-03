import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from unittest.mock import patch, MagicMock
from bot_api import get_fixtures, get_analysis, get_insight

def _mock_fixtures():
    return [
        {
            "id": "1", "home_id": "42", "away_id": "99",
            "home_name": "River Plate", "away_name": "Boca Juniors",
            "home_logo": "", "away_logo": "",
            "date": "2025-06-03T21:00:00Z", "status": "Scheduled", "completed": False
        }
    ]

def _mock_analysis():
    return {
        "prediction": {"best_bet": "Local", "confidence": 60, "prob_home": 55, "prob_draw": 25, "prob_away": 20,
                       "btts_prob": 45, "home_expected_goals": 1.5, "away_expected_goals": 0.9},
        "home_form": {"form": "WWDLL", "avg_goals_for": 1.8, "avg_goals_against": 1.1,
                      "avg_possession": 55.0, "avg_shots": 14.0, "avg_shots_on": 5.0,
                      "avg_fouls": 10.0, "avg_corners": 5.5, "avg_yellow_cards": 2.1,
                      "matches_analyzed": 10, "competitions_count": 2,
                      "top_scorers": [], "top_assists": [], "top_cards": []},
        "away_form": {"form": "WDLLL", "avg_goals_for": 1.2, "avg_goals_against": 1.4,
                      "avg_possession": 48.0, "avg_shots": 11.0, "avg_shots_on": 4.0,
                      "avg_fouls": 12.0, "avg_corners": 4.5, "avg_yellow_cards": 2.8,
                      "matches_analyzed": 10, "competitions_count": 2,
                      "top_scorers": [], "top_assists": [], "top_cards": []},
        "h2h": {"home_wins": 3, "away_wins": 2, "draws": 1, "total": 6},
        "mood_alerts": []
    }

def _mock_insight():
    return {
        "estilo_local": "River juega con posesión.",
        "estilo_visitante": "Boca presiona alto.",
        "desarrollo_partido": "Partido trabado en el medio.",
        "resultado_probable": "River 2-1 Boca",
        "corners": {"min": 8, "max": 11, "pick": 9.5},
        "amarillas": {"min": 3, "max": 5, "pick": 4.0},
        "parlay": {"picks": ["River gana", "Más de 9.5 corners"], "razon": "River dominante."}
    }

def test_get_fixtures_returns_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_fixtures()
    mock_resp.raise_for_status = MagicMock()
    with patch('bot_api.requests.get', return_value=mock_resp):
        result = get_fixtures("Liga Argentina")
    assert len(result) == 1
    assert result[0]["home_name"] == "River Plate"

def test_get_fixtures_returns_empty_on_error():
    with patch('bot_api.requests.get', side_effect=Exception("timeout")):
        result = get_fixtures("Liga Argentina")
    assert result == []

def test_get_analysis_returns_dict():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_analysis()
    mock_resp.raise_for_status = MagicMock()
    with patch('bot_api.requests.get', return_value=mock_resp):
        result = get_analysis("Liga Argentina", "arg.1", "arg.1", "42", "99", "River", "Boca")
    assert result["prediction"]["best_bet"] == "Local"

def test_get_analysis_returns_none_on_error():
    with patch('bot_api.requests.get', side_effect=Exception("timeout")):
        result = get_analysis("Liga Argentina", "arg.1", "arg.1", "42", "99", "River", "Boca")
    assert result is None

def test_get_insight_returns_dict():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _mock_insight()
    mock_resp.raise_for_status = MagicMock()
    with patch('bot_api.requests.post', return_value=mock_resp):
        result = get_insight(_mock_analysis(), "River", "Boca", "42", "99", "arg.1", "arg.1")
    assert result["resultado_probable"] == "River 2-1 Boca"

def test_get_insight_returns_none_on_error():
    with patch('bot_api.requests.post', side_effect=Exception("timeout")):
        result = get_insight(_mock_analysis(), "River", "Boca", "42", "99", "arg.1", "arg.1")
    assert result is None
