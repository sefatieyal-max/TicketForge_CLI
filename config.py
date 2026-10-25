"""Load and save the connection settings created by the `setup` command.

The config file holds only non-secret settings (base URL, username).
The password is taken from an environment variable, the OS credential
store (via `keyring`, if installed), or a hidden prompt, in that order.
"""

import json
import os
from pathlib import Path

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:            # keyring is optional
    keyring = None
    KeyringError = Exception

CONFIG_DIR_ENV = "TICKETFORGE_CONFIG_DIR"
PASSWORD_ENV = "TICKETFORGE_PASSWORD"
DEFAULT_CONFIG_DIR = Path.home() / ".ticketforge"
CONFIG_FILE_NAME = "config.json"
KEYRING_SERVICE = "ticketforge-cli"


class ConfigError(Exception):
    """The config file is missing or unreadable."""


def config_path():
    """Path of the config file (overridable for tests via an env var)."""
    directory = Path(os.environ.get(CONFIG_DIR_ENV) or DEFAULT_CONFIG_DIR)
    return directory / CONFIG_FILE_NAME


def load_config():
    """Return the saved settings dict. Raises ConfigError if setup was never run."""
    path = config_path()
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        raise ConfigError("TicketForge is not configured yet. Run: python main.py setup") from None
    except (OSError, ValueError):
        raise ConfigError(f"Could not read {path}. Run setup again.") from None
    if not isinstance(data, dict) or not data.get("username") or not data.get("base_url"):
        raise ConfigError(f"{path} is incomplete. Run setup again.")
    return data


def save_config(base_url, username):
    """Write the non-secret settings and return the file path."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump({"base_url": base_url, "username": username}, file, indent=2)
    return path


def read_saved_password(username):
    """Password from the env var or the OS credential store, or None."""
    from_env = (os.environ.get(PASSWORD_ENV) or "").strip()
    if from_env:
        return from_env
    if keyring is None:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, username)
    except KeyringError:
        return None


def store_password(username, password):
    """Save the password in the OS credential store. Returns True on success."""
    if keyring is None:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, username, password)
    except KeyringError:
        return False
    return True

def delete_password(username):
    """Remove a saved password from the OS credential store. Returns True if one was removed."""
    if keyring is None:
        return False
    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except KeyringError:            # includes "no such password"
        return False
    return True