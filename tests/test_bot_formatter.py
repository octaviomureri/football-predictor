import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot_formatter import format_fixtures_list, format_insight_message, format_no_fixtures

def _sample_fixtures():
    return [
        {"id": "1", "home_id": "42", "away_id": "99",
         "home_name": "River Plate", "away_name": "Boca Juniors",
         "date": "2025-06-03T21:00:00Z", "completed": False},
        {"id": "2", "home_id": "10", "away_id": "20",
         "home_name": "Racing", "away_name": "Independiente",
         "date": "2025-06-03T19:00:00Z", "completed": True},
    ]

def _sample_insight():
    return {
        "estilo_local": "River juega con posesión.",
        "estilo_visitante": "Boca presiona alto.",
        "desarrollo_partido": "Partido trabado en el medio.",
        "resultado_probable": "River 2-1 Boca",
        "corners": {"min": 8, "max": 11, "pick": 9.5},
        "amarillas": {"min": 3, "max": 5, "pick": 4.0},
        "parlay": {"picks": ["River gana", "Más de 9.5 corners"], "razon": "River dominante."}
    }

def test_format_fixtures_list_contains_team_names():
    text = format_fixtures_list(_sample_fixtures(), "Liga Argentina")
    assert "River Plate" in text
    assert "Boca Juniors" in text
    assert "Liga Argentina" in text

def test_format_fixtures_list_shows_completed_indicator():
    text = format_fixtures_list(_sample_fixtures(), "Liga Argentina")
    assert "✅" in text or "⚪" in text or "🟢" in text

def test_format_insight_message_contains_key_sections():
    text = format_insight_message("River Plate", "Boca Juniors", "Liga Argentina", _sample_insight())
    assert "River Plate" in text
    assert "Boca Juniors" in text
    assert "River 2-1 Boca" in text
    assert "9.5" in text
    assert "River gana" in text
    assert "PARLAY" in text.upper()

def test_format_insight_message_handles_missing_parlay():
    insight = _sample_insight()
    insight["parlay"] = {}
    text = format_insight_message("River", "Boca", "Liga Argentina", insight)
    assert "River" in text  # No crash

def test_format_no_fixtures_returns_string():
    text = format_no_fixtures("Premier League")
    assert "Premier League" in text
    assert isinstance(text, str)
