"""Pure input parsers.

Each function takes raw user text and returns the normalized value,
or None when the input is certainly invalid. No printing, no network.
"""

import re

REF_PREFIX = "TF-"
REF_PATTERN = re.compile(r"TF-\d+")
STAGES = ("open", "in_progress", "review", "closed")
REF_LIST_SEPARATOR = ","
BASIC_AUTH_SEPARATOR = ":"
MAX_USERNAME_LENGTH = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 50


def parse_ref(text):
    """'tf-12', 'TF-12', '#12' or '12' -> 'TF-12'."""
    value = (text or "").strip().upper().lstrip("#")
    if value.isdecimal():
        value = f"{REF_PREFIX}{value}"
    return value if REF_PATTERN.fullmatch(value) else None


def parse_ref_list(text):
    """'TF-1, 2' -> ['TF-1', 'TF-2']. Empty text -> []. Any invalid item -> None."""
    items = [item for item in (text or "").split(REF_LIST_SEPARATOR) if item.strip()]
    refs = [parse_ref(item) for item in items]
    if any(ref is None for ref in refs):
        return None
    return list(dict.fromkeys(refs))  # drop duplicates, keep order


def parse_stage(text):
    """'In Progress', 'in-progress' -> 'in_progress'."""
    value = re.sub(r"[\s-]+", "_", (text or "").strip().lower())
    return value if value in STAGES else None


def parse_title(text):
    """Non-empty, trimmed title. Length limits are left to the API."""
    value = (text or "").strip()
    return value or None


def parse_username(text):
    """Trimmed username without ':' (it would break Basic auth)."""
    value = (text or "").strip()
    if not value or BASIC_AUTH_SEPARATOR in value or len(value) > MAX_USERNAME_LENGTH:
        return None
    return value


def parse_page_size(text):
    """Whole number in the allowed page-size range."""
    value = (text or "").strip()
    if not value.isdecimal():
        return None
    number = int(value)
    return number if MIN_PAGE_SIZE <= number <= MAX_PAGE_SIZE else None
