from unittest.mock import patch

import prompts


def test_password_keeps_surrounding_spaces():
    with patch("prompts.getpass", return_value="  pass  "):
        assert prompts.ask_password() == "  pass  "


def test_spaces_only_password_is_not_cancel():
    with patch("prompts.getpass", return_value="   "):
        assert prompts.ask_password() == "   "


def test_empty_password_means_cancel():
    with patch("prompts.getpass", return_value=""):
        assert prompts.ask_password() is None