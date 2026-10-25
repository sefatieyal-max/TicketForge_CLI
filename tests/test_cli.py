from unittest.mock import patch

import pytest

import cli
import config
from exceptions import AuthError, NotFoundError

TICKET = {"ref": "TF-1", "title": "t", "description": "keep me", "stage": "open",
          "dependsOn": ["TF-2"], "customFields": {}}


class FakeClient:
    """Stands in for the real client: no network, records what was sent."""

    def __init__(self, ticket=None):
        self.ticket = ticket
        self.updates = []
        self.username = "eyal"
        self.rate_remaining = None
        self.rate_limit = None

    def get_ticket(self, ref):
        if self.ticket is None:
            raise NotFoundError("not found")
        return self.ticket

    def update_ticket(self, ref, **fields):
        self.updates.append(fields)
        return {"ref": ref}


def test_update_keeps_fields_that_were_not_changed():
    client = FakeClient(TICKET)
    with patch("builtins.input", side_effect=["y"]):
        cli.TicketForgeCLI(client).update_ticket("TF-1", {"stage": "review"})
    assert client.updates == [{"title": "t", "description": "keep me", "stage": "review",
                               "depends_on": ["TF-2"], "custom_fields": {}}]


def test_update_is_not_sent_when_user_declines():
    client = FakeClient(TICKET)
    with patch("builtins.input", side_effect=["n"]):
        cli.TicketForgeCLI(client).update_ticket("TF-1", {"stage": "review"})
    assert client.updates == []


def test_update_without_changes_sends_nothing():
    client = FakeClient(TICKET)
    with patch("builtins.input", side_effect=["", "", ""]):     # Enter on every prompt
        cli.TicketForgeCLI(client).update_ticket("TF-1")
    assert client.updates == []


def test_missing_ticket_shows_friendly_message(capsys):
    cli.TicketForgeCLI(FakeClient(ticket=None)).show_ticket("TF-9")
    assert "TF-9 was not found" in capsys.readouterr().err

class AlwaysWrongPasswordClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.checks = 0

    def verify_credentials(self):
        self.checks += 1
        raise AuthError("wrong")

    def set_password(self, password):
        pass


def test_login_gives_up_after_max_attempts():
    client = AlwaysWrongPasswordClient()
    # each retry: "switch user?" -> n, then a new password
    with patch("builtins.input", side_effect=["n", "n"]), patch("prompts.getpass", side_effect=["a", "b"]):
        assert cli.TicketForgeCLI(client)._login() is False
    assert client.checks == cli.MAX_LOGIN_ATTEMPTS


def test_menu_rejects_unknown_choice_then_exits(capsys):
    client = FakeClient()
    client.verify_credentials = lambda: None
    with patch("builtins.input", side_effect=["9", "abc", cli.EXIT_CHOICE]):
        cli.TicketForgeCLI(client).run_menu()
    assert capsys.readouterr().err.count("Please choose one of") == 2

# ---------- setup / switch user / logout ----------

class SetupClient:
    """Replaces TicketForgeClient inside run_setup."""
    instances = []

    def __init__(self, username, password, base_url=None):
        self.username, self.password, self.base_url = username, password, base_url
        self.registered = False
        SetupClient.instances.append(self)

    def register(self, username, password):
        self.registered = True

    def verify_credentials(self):
        if self.password != "good":
            raise AuthError("Invalid username or password.")


@pytest.fixture
def setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv(config.CONFIG_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(cli, "TicketForgeClient", SetupClient)
    monkeypatch.setattr(config, "store_password", lambda username, password: True)
    SetupClient.instances.clear()
    return tmp_path


def test_setup_cancelled_on_empty_username(setup_env):
    with patch("builtins.input", side_effect=["", ""]):        # URL default, then Enter at username
        assert cli.run_setup() is None
    assert not (setup_env / config.CONFIG_FILE_NAME).exists()


def test_setup_with_existing_account_saves_config(setup_env):
    with patch("builtins.input", side_effect=["", "eyal", "y", "n"]), patch("prompts.getpass", return_value="good"):
        client = cli.run_setup()
    assert client.username == "eyal" and client.registered is False
    assert config.load_config()["username"] == "eyal"


def test_setup_registers_new_account(setup_env):
    with patch("builtins.input", side_effect=["", "newbie", "n", "n"]), patch("prompts.getpass", return_value="good"):
        client = cli.run_setup()
    assert client.registered is True


def test_setup_with_wrong_password_does_not_save_config(setup_env):
    with patch("builtins.input", side_effect=["", "eyal", "y"]), patch("prompts.getpass", return_value="bad"):
        with pytest.raises(AuthError):
            cli.run_setup()
    assert not (setup_env / config.CONFIG_FILE_NAME).exists()


def test_switch_user_replaces_client_on_success():
    new_client = FakeClient()
    app = cli.TicketForgeCLI(FakeClient())
    with patch("cli.run_setup", return_value=new_client):
        assert app.switch_user() is True
    assert app.client is new_client


def test_switch_user_cancelled_keeps_current_client():
    old_client = FakeClient()
    app = cli.TicketForgeCLI(old_client)
    with patch("cli.run_setup", return_value=None):
        assert app.switch_user() is False
    assert app.client is old_client


def test_login_enter_quits_without_more_requests():
    client = AlwaysWrongPasswordClient()
    with patch("builtins.input", side_effect=["n"]), patch("prompts.getpass", return_value=""):
        assert cli.TicketForgeCLI(client)._login() is False
    assert client.checks == 1


def test_logout_removes_saved_password(capsys):
    with patch("cli.config.delete_password", return_value=True) as delete:
        cli.TicketForgeCLI(FakeClient()).logout()
    delete.assert_called_once_with("eyal")
    assert "removed" in capsys.readouterr().out


def test_logout_without_saved_password_says_so(capsys):
    with patch("cli.config.delete_password", return_value=False):
        cli.TicketForgeCLI(FakeClient()).logout()
    assert "No saved password" in capsys.readouterr().out


def test_menu_logout_choice_exits_the_menu():
    client = FakeClient()
    client.verify_credentials = lambda: None
    with patch("builtins.input", side_effect=[cli.LOGOUT_CHOICE]), \
            patch("cli.config.delete_password", return_value=True):
        cli.TicketForgeCLI(client).run_menu()       # returns instead of waiting for more input