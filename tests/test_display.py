import display


def test_truncate_keeps_short_text():
    assert display.truncate("abc", 10) == "abc"


def test_truncate_cuts_long_text_to_exact_width():
    result = display.truncate("a" * 50, 10)
    assert len(result) == 10
    assert result.endswith(display.ELLIPSIS)


def test_format_datetime_handles_missing_and_garbage():
    assert display.format_datetime(None) == display.EMPTY_PLACEHOLDER
    assert display.format_datetime("not a date") == "not a date"


def test_format_status_without_budget_shows_only_user():
    assert display.format_status("eyal", None, None) == "Logged in as eyal"