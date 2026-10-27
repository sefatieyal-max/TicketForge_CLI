from unittest.mock import patch

import main


def test_cancelled_password_prompt_exits_with_failure():
    with patch("main.cli.build_client", return_value=None):
        assert main.main(["list"]) == main.EXIT_FAILURE