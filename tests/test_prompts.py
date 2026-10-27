from unittest.mock import patch
import pytest
import prompts

@pytest.mark.parametrize("answers, expected", [
    ([""], True),
    (["q"], False),
    (["Q"], False),
    (["x", "y", ""], True),      # unknown keys are asked again, then Enter
    (["more", "q"], False),
])

def test_ask_more(answers, expected):
    with patch("builtins.input", side_effect=answers):
        assert prompts.ask_more() is expected


def test_password_keeps_surrounding_spaces():
    with patch("prompts.getpass", return_value="  pass  "):
        assert prompts.ask_password() == "  pass  "


def test_spaces_only_password_is_not_cancel():
    with patch("prompts.getpass", return_value="   "):
        assert prompts.ask_password() == "   "


def test_empty_password_means_cancel():
    with patch("prompts.getpass", return_value=""):
        assert prompts.ask_password() is None