import json
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import app as flask_app
import pytest

@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c

def _sample_analysis():
    form = {
        "form": "WWDLL", "avg_goals_for": 1.5, "avg_goals_against": 1.0,
        "avg_possession": 52.0, "avg_shots": 13.0, "avg_shots_on": 4.5,
        "avg_fouls": 10.0, "avg_corners": 5.0, "avg_yellow_cards": 2.0,
        "matches_analyzed": 10, "competitions_count": 2,
        "top_scorers": [], "top_assists": [], "top_cards": [],
    }
    return {
        "prediction": {"prob_home": 45, "prob_draw": 25, "prob_away": 30,
                       "btts_prob": 55, "best_bet": "Local", "confidence": 45,
                       "home_expected_goals": 1.5, "away_expected_goals": 1.0},
        "home_form": form, "away_form": form,
        "h2h": {"home_wins": 2, "away_wins": 1, "draws": 1, "total": 4},
        "mood_alerts": [],
    }

def test_match_insight_returns_insight_json(client):
    insight = {
        "estilo_local": "Equipo vertical", "estilo_visitante": "Posesión",
        "desarrollo_partido": "Partido abierto",
        "resultado_probable": "Local 2-1 Visitante",
        "corners": {"min": 7, "max": 10, "pick": 8.5},
        "amarillas": {"min": 2, "max": 4, "pick": 3},
        "parlay": {"picks": ["Local gana"], "razon": "Dominante en casa"}
    }
    payload = {
        "home_name": "Local", "away_name": "Visitante",
        "home_id": "1", "away_id": "2",
        "home_slug": "eng.1", "away_slug": "eng.1",
        "home_form": {}, "away_form": {}, "h2h": {}, "alerts": []
    }
    with patch('app.get_team_injuries', return_value=[]), \
         patch('app.get_match_insight', return_value=insight):
        res = client.post('/api/match-insight',
                         json=payload,
                         content_type='application/json')
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["resultado_probable"] == "Local 2-1 Visitante"
    assert data["corners"]["pick"] == 8.5

def test_match_insight_returns_error_on_failure(client):
    with patch('app.get_match_insight', side_effect=Exception("Claude down")):
        res = client.post('/api/match-insight',
                         json={"home_name": "A", "away_name": "B",
                               "home_form": {}, "away_form": {}, "h2h": {}, "alerts": []},
                         content_type='application/json')
    assert res.status_code == 500
    data = json.loads(res.data)
    assert "error" in data
