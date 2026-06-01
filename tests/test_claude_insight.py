import json
from unittest.mock import patch, MagicMock
from claude_insight import build_prompt, generate_insight

def _sample_form():
    return {
        "form": "WWDLL",
        "avg_goals_for": 1.8,
        "avg_goals_against": 1.1,
        "avg_possession": 55.0,
        "avg_shots": 14.0,
        "avg_shots_on": 5.0,
        "avg_fouls": 11.0,
        "avg_corners": 5.5,
        "avg_yellow_cards": 2.1,
        "top_scorers": [{"name": "Jugador A", "goals": 5}],
        "top_assists": [{"name": "Jugador B", "assists": 3}],
    }

def test_build_prompt_contains_team_names():
    prompt = build_prompt(
        home_name="River", away_name="Boca",
        home_form=_sample_form(), away_form=_sample_form(),
        h2h={"home_wins": 2, "away_wins": 1, "draws": 1, "total": 4},
        home_injured=["Jugador C"], away_injured=[],
        alerts=[]
    )
    assert "River" in prompt
    assert "Boca" in prompt
    assert "Jugador C" in prompt

def test_build_prompt_contains_stat_keys():
    prompt = build_prompt(
        home_name="River", away_name="Boca",
        home_form=_sample_form(), away_form=_sample_form(),
        h2h={"home_wins": 0, "away_wins": 0, "draws": 0, "total": 0},
        home_injured=[], away_injured=[],
        alerts=[]
    )
    assert "corners" in prompt.lower()
    assert "amarillas" in prompt.lower() or "yellow" in prompt.lower()

def test_generate_insight_returns_parsed_json():
    expected = {
        "estilo_local": "Juega directo",
        "estilo_visitante": "Posesión alta",
        "desarrollo_partido": "Partido trabado",
        "resultado_probable": "River 1-0 Boca",
        "corners": {"min": 7, "max": 10, "pick": 8.5},
        "amarillas": {"min": 3, "max": 5, "pick": 4},
        "parlay": {
            "picks": ["River gana", "Más de 8.5 corners"],
            "razon": "River dominante en casa"
        }
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(expected))
    ]
    with patch('claude_insight.anthropic.Anthropic', return_value=mock_client), \
         patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'sk-test-key'}):
        result = generate_insight("prompt de prueba")
    assert result["resultado_probable"] == "River 1-0 Boca"
    assert result["corners"]["pick"] == 8.5
    assert len(result["parlay"]["picks"]) == 2

def test_generate_insight_returns_error_dict_on_failure():
    with patch('claude_insight.anthropic.Anthropic', side_effect=Exception("API error")):
        result = generate_insight("prompt")
    assert "error" in result
