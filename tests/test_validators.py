from datetime import datetime, timezone
import pytest
import validators


@pytest.mark.parametrize("text, expected", [
    ("TF-12", "TF-12"),
    (" tf-12 ", "TF-12"),
    ("#12", "TF-12"),
    ("12", "TF-12"),
    ("TF-", None),
    ("tf-7x", None),
    ("../user", None),
    ("", None),
])
def test_parse_ref(text, expected):
    assert validators.parse_ref(text) == expected


def test_parse_ref_list_normalizes_and_drops_duplicates():
    assert validators.parse_ref_list("1, TF-2,1") == ["TF-1", "TF-2"]


def test_parse_ref_list_rejects_any_invalid_item():
    assert validators.parse_ref_list("TF-1, abc") is None


@pytest.mark.parametrize("text, expected", [
    ("In Progress", "in_progress"),
    ("in-progress", "in_progress"),
    ("CLOSED", "closed"),
    ("done", None),
])
def test_parse_stage(text, expected):
    assert validators.parse_stage(text) == expected


def test_parse_username_rejects_colon_because_it_breaks_basic_auth():
    assert validators.parse_username("eyal:1") is None


@pytest.mark.parametrize("text, expected", [
    ("1", 1),
    ("50", 50),
    ("0", None),
    ("51", None),
    ("abc", None),
])
def test_parse_page_size_boundaries(text, expected):
    assert validators.parse_page_size(text) == expected

@pytest.mark.parametrize("text, expected", [
    ("abc123", True),
    ("café", True),
    ("סיסמה", False),
])
def test_is_basic_auth_safe(text, expected):
    assert validators.is_basic_auth_safe(text) is expected


def test_parse_username_rejects_non_latin():
    assert validators.parse_username("אייל") is None



def test_parse_iso_datetime_handles_z_suffix():
    assert validators.parse_iso_datetime("2026-10-25T08:20:35.944Z") == \
        datetime(2026, 10, 25, 8, 20, 35, 944000, tzinfo=timezone.utc)


@pytest.mark.parametrize("text", [None, "", "not a date"])
def test_parse_iso_datetime_returns_none_for_bad_input(text):
    assert validators.parse_iso_datetime(text) is None