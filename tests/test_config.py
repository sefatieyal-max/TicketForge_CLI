import pytest

import config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Point the config at a temporary folder so tests never touch the real one."""
    monkeypatch.setenv(config.CONFIG_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(config.PASSWORD_ENV, raising=False)
    return tmp_path


def test_load_without_setup_raises_config_error(config_dir):
    with pytest.raises(config.ConfigError, match="not configured"):
        config.load_config()


def test_save_then_load_round_trip(config_dir):
    config.save_config("https://example.com", "eyal")
    assert config.load_config() == {"base_url": "https://example.com", "username": "eyal"}


def test_password_is_never_written_to_the_config_file(config_dir):
    path = config.save_config("https://example.com", "eyal")
    assert "password" not in path.read_text(encoding="utf-8")


def test_corrupted_config_raises_config_error(config_dir):
    (config_dir / config.CONFIG_FILE_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="Could not read"):
        config.load_config()


def test_incomplete_config_raises_config_error(config_dir):
    (config_dir / config.CONFIG_FILE_NAME).write_text('{"username": ""}', encoding="utf-8")
    with pytest.raises(config.ConfigError, match="incomplete"):
        config.load_config()


def test_env_password_wins_over_keyring(config_dir, monkeypatch):
    monkeypatch.setenv(config.PASSWORD_ENV, " from-env ")
    assert config.read_saved_password("eyal") == "from-env"


def test_no_keyring_means_no_saved_password(config_dir, monkeypatch):
    monkeypatch.setattr(config, "keyring", None)
    assert config.read_saved_password("eyal") is None
    assert config.store_password("eyal", "x") is False
    assert config.delete_password("eyal") is False
