"""Generic input helpers: how we ask the user things.

Each function does one job. cli.py decides what to ask; this module only
knows how to ask, re-ask, and hide passwords.
"""

from getpass import getpass

import display

YES_ANSWERS = {"y", "yes"}
NO_ANSWERS = {"n", "no"}


def ask(prompt):
    """Trimmed input. Empty input returns None."""
    return input(prompt).strip() or None


def ask_valid(prompt, parse, example):
    """Re-ask until `parse` accepts the input. Enter returns None (cancel)."""
    while True:
        text = ask(prompt)
        if text is None:
            return None
        value = parse(text)
        if value is not None:
            return value
        display.print_error(f"Invalid value. Example: {example}")


def confirm(question):
    """Explicit y/n, no default. Re-asks until the answer is clear."""
    while True:
        answer = (input(f"{question} [y/n]: ").strip().lower())
        if answer in YES_ANSWERS:
            return True
        if answer in NO_ANSWERS:
            return False
        display.print_error("Please answer y or n.")


def ask_password(prompt="Password: "):
    """Hidden input. Empty input returns None."""
    return getpass(prompt).strip() or None
