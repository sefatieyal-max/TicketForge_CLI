"""All formatting and printing.

format_* functions return strings (easy to test); print_* functions print.
Nothing here makes decisions or talks to the API.
"""

import os
import sys
from datetime import datetime

try:
    import colorama
    colorama.just_fix_windows_console()
except ImportError:            # colors still work in most modern terminals
    pass

NO_COLOR_ENV = "NO_COLOR"      # https://no-color.org convention
EMPTY_PLACEHOLDER = "-"
DATE_DISPLAY_FORMAT = "%Y-%m-%d %H:%M"
ELLIPSIS = "..."
REF_WIDTH = 8
STAGE_WIDTH = 12
TITLE_WIDTH = 40
DATE_WIDTH = 16
LABEL_WIDTH = 12

RESET = "\033[0m"
STAGE_COLORS = {
    "open": "\033[34m",         # blue
    "in_progress": "\033[33m",  # yellow
    "review": "\033[35m",       # magenta
    "closed": "\033[32m",       # green
}
ERROR_COLOR = "\033[31m"
SUCCESS_COLOR = "\033[32m"
TITLE_DECORATION = "==="



def colors_enabled():
    """Color only real terminals, and respect NO_COLOR."""
    return sys.stdout.isatty() and not os.environ.get(NO_COLOR_ENV)


def colorize(text, color):
    return f"{color}{text}{RESET}" if color and colors_enabled() else text


def truncate(text, width):
    text = str(text)
    return text if len(text) <= width else text[: width - len(ELLIPSIS)] + ELLIPSIS


def format_datetime(iso_text):
    """'2026-10-25T08:20:35.944Z' -> '2026-10-25 10:20' in local time."""
    if not iso_text:
        return EMPTY_PLACEHOLDER
    try:
        return datetime.fromisoformat(iso_text).astimezone().strftime(DATE_DISPLAY_FORMAT)
    except (TypeError, ValueError):
        return str(iso_text)


def format_stage(stage):
    """Pad first, then color, so ANSI codes don't break column alignment."""
    padded = f"{stage or EMPTY_PLACEHOLDER:<{STAGE_WIDTH}}"
    return colorize(padded, STAGE_COLORS.get(stage))


def format_ticket_row(ticket):
    return (
        f"{ticket.get('ref', EMPTY_PLACEHOLDER):<{REF_WIDTH}}  "
        f"{format_stage(ticket.get('stage'))}  "
        f"{truncate(ticket.get('title') or EMPTY_PLACEHOLDER, TITLE_WIDTH):<{TITLE_WIDTH}}  "
        f"{format_datetime(ticket.get('updated')):<{DATE_WIDTH}}"
    )


def format_table_header():
    return (
        f"{'REF':<{REF_WIDTH}}  {'STAGE':<{STAGE_WIDTH}}  "
        f"{'TITLE':<{TITLE_WIDTH}}  {'UPDATED':<{DATE_WIDTH}}"
    )


def format_rate_limit(remaining, limit):
    if remaining is None or limit is None:
        return ""
    return f"API requests left: {remaining}/{limit}"


def format_list(values):
    return ", ".join(values) if values else EMPTY_PLACEHOLDER


def format_custom_fields(values, labels):
    """{'size': 'L'} with labels {'size': 'Size'} -> 'Size: L'."""
    if not values:
        return EMPTY_PLACEHOLDER
    return ", ".join(f"{labels.get(name, name)}: {value}" for name, value in values.items())

def format_change(field, old_value, new_value):
    """'stage: open  ->  review'."""
    return f"  {field}: {old_value or EMPTY_PLACEHOLDER}  ->  {new_value or EMPTY_PLACEHOLDER}"


def print_changes(before, after):
    """Print only the fields whose value differs."""
    print("\nChanges:")
    for field, new_value in after.items():
        if new_value != before.get(field):
            print(format_change(field, before.get(field), new_value))


def print_ticket_table(tickets):
    print(format_table_header())
    print("-" * len(format_table_header()))
    for ticket in tickets:
        print(format_ticket_row(ticket))


def print_fields(pairs):
    """Aligned 'label: value' block."""
    for label, value in pairs:
        print(f"{label + ':':<{LABEL_WIDTH}} {value}")


def print_ticket_details(ticket, field_labels=None):
    owner = ticket.get("owner") or {}
    print_fields([
        ("Ref", ticket.get("ref", EMPTY_PLACEHOLDER)),
        ("Title", ticket.get("title") or EMPTY_PLACEHOLDER),
        ("Stage", format_stage(ticket.get("stage")).rstrip()),
        ("Owner", owner.get("username") or EMPTY_PLACEHOLDER),
        ("Depends on", format_list(ticket.get("dependsOn"))),
        ("Fields", format_custom_fields(ticket.get("customFields"), field_labels or {})),
        ("Created", format_datetime(ticket.get("created"))),
        ("Updated", format_datetime(ticket.get("updated"))),
    ])
    print(f"\n{ticket.get('description') or '(no description)'}")


def print_success(message):
    print(colorize(f"[ok] {message}", SUCCESS_COLOR))


def print_error(message):
    print(colorize(f"[!] {message}", ERROR_COLOR), file=sys.stderr)


def print_info(message):
    if message:
        print(message)

# ------------------- format and print title + menu ----------------------------
def format_title(text):
    """'TicketForge' -> '=== TicketForge ==='."""
    return f"{TITLE_DECORATION} {text} {TITLE_DECORATION}"


def format_menu(title, options, exit_key, status):
    """options: {key: label} -> the menu text, with the exit option last."""
    lines = [f"\n{format_title(title)}"]
    if status:
        lines.append(status)
    lines += [f"  {key}. {label}" for key, label in options.items()]
    lines.append(f"  {exit_key}. Exit")
    return "\n".join(lines)


def print_menu(title, options, exit_key, status=""):
    print(format_menu(title, options, exit_key, status))


def format_status(username, remaining, limit):
    """'Logged in as Eyal | API requests left: 47/50'."""
    status = f"Logged in as {username or EMPTY_PLACEHOLDER}"
    budget = format_rate_limit(remaining, limit)
    return f"{status} | {budget}" if budget else status