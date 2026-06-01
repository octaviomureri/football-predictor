from unittest.mock import patch, MagicMock
from api_client import get_team_injuries

def test_get_team_injuries_returns_list_of_names():
    mock_response = {
        "injuries": [
            {
                "team": {"id": "42"},
                "injuries": [
                    {"athlete": {"displayName": "John Doe"}, "status": "Out"},
                    {"athlete": {"displayName": "Jane Smith"}, "status": "Questionable"},
                ]
            },
            {
                "team": {"id": "99"},
                "injuries": [
                    {"athlete": {"displayName": "Other Player"}, "status": "Out"},
                ]
            }
        ]
    }
    with patch('api_client.get', return_value=mock_response):
        result = get_team_injuries("42", "eng.1")
    assert result == ["John Doe"]  # Jane Smith filtered (Questionable)

def test_get_team_injuries_accepts_integer_team_id():
    mock_response = {
        "injuries": [
            {
                "team": {"id": "42"},
                "injuries": [
                    {"athlete": {"displayName": "John Doe"}, "status": "Out"},
                ]
            }
        ]
    }
    with patch('api_client.get', return_value=mock_response):
        result = get_team_injuries(42, "eng.1")  # integer, not string
    assert result == ["John Doe"]

def test_get_team_injuries_returns_empty_on_failure():
    with patch('api_client.get', side_effect=Exception("Network error")):
        result = get_team_injuries("42", "eng.1")
    assert result == []

def test_get_team_injuries_returns_empty_when_team_not_found():
    mock_response = {
        "injuries": [
            {
                "team": {"id": "99"},
                "injuries": [{"athlete": {"displayName": "Other"}, "status": "Out"}]
            }
        ]
    }
    with patch('api_client.get', return_value=mock_response):
        result = get_team_injuries("42", "eng.1")
    assert result == []
