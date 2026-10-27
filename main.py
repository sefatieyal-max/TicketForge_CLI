"""Entry point: parse the command line and dispatch to the CLI.

Every command runs inside one safety net that turns our exceptions into
friendly messages and a non-zero exit code. No traceback reaches the user.
"""

import argparse
import sys

import cli
import display
from client import DEFAULT_PAGE_SIZE
from config import ConfigError
from exceptions import TicketForgeError
from validators import parse_page_size, parse_ref, parse_ref_list, parse_title, parse_stage

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130          #Ctrl + c


def validated(parse, message):
    """Turn one of our validators into an argparse `type` (rules stay in validators.py)."""
    def convert(text):
        value = parse(text)
        if value is None:
            raise argparse.ArgumentTypeError(message)
        return value
    return convert

# ------------------- parse and validate types ---------------------------------
PAGE_SIZE_TYPE = validated(parse_page_size, "must be a whole number between 1 and 50")
REF_TYPE = validated(parse_ref, "expected a ref number like TF-12 or 12")
TITLE_TYPE = validated(parse_title, "title cannot be empty")
REFS_TYPE = validated(parse_ref_list, "expected comma-separated refs like TF-1,TF-2")
STAGE_TYPE = validated(parse_stage, "expected one of: open, in_progress, review, closed")



def build_parser():
    parser = argparse.ArgumentParser(prog="ticketforge", description="Manage TicketForge tickets from the terminal.")
    commands = parser.add_subparsers(dest="command", required=False )

    commands.add_parser("setup", help="Configure and verify your TicketForge connection")

    list_cmd = commands.add_parser("list", help="List your tickets")
    list_cmd.add_argument("--limit", type=PAGE_SIZE_TYPE, default=DEFAULT_PAGE_SIZE, help="tickets per page (1-50)")
    list_cmd.add_argument("--all", action="store_true", help="fetch every page without asking")
    show_cmd = commands.add_parser("show", help="Show one ticket")
    show_cmd.add_argument("ref", type=REF_TYPE, help="ticket ref, e.g. TF-12 or 12")
    create_cmd = commands.add_parser("create", help="Create a ticket (asks for anything not given)")
    create_cmd.add_argument("--title", type=TITLE_TYPE, help="ticket title")
    create_cmd.add_argument("--description", help="ticket description")
    create_cmd.add_argument("--depends-on", type=REFS_TYPE, help="comma-separated refs, e.g. TF-1,TF-2")
    update_cmd = commands.add_parser("update", help="Update a ticket (interactive if no options are given)")
    update_cmd.add_argument("ref", type=REF_TYPE, help="ticket ref, e.g. TF-12 or 12")
    update_cmd.add_argument("--title", type=TITLE_TYPE, help="new title")
    update_cmd.add_argument("--description", help="new description")
    update_cmd.add_argument("--stage", type=STAGE_TYPE, help="open, in_progress, review or closed")
    update_cmd.add_argument("--depends-on", type=REFS_TYPE, help="comma-separated refs, e.g. TF-1,TF-2")
    return parser


def update_changes(args):
    """Only the options the user actually passed. Empty dict -> interactive edit."""
    changes = {
        "title": args.title,
        "description": args.description,
        "stage": args.stage,
        "depends_on": args.depends_on,
    }
    return {key: value for key, value in changes.items() if value is not None}

def run_command(args):
    """Dispatch one command. Returns an exit code."""
    if args.command == "setup":
        return EXIT_SUCCESS if cli.run_setup() is not None else EXIT_FAILURE

    app = cli.TicketForgeCLI(cli.build_client())
    match args.command:
        case "list":
            app.list_tickets(args.limit, show_all=args.all)
        case "show":
            app.show_ticket(args.ref)
        case "create":
            app.create_ticket(args.title, args.description, args.depends_on)
        case "update":
            app.update_ticket(args.ref, update_changes(args))
        case None:
            return EXIT_SUCCESS if app.run_menu() else EXIT_FAILURE

    return EXIT_SUCCESS


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return run_command(args)
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")
        return EXIT_INTERRUPTED
    except ConfigError as error:
        display.print_error(str(error))
    except TicketForgeError as error:        # safety net: any API error
        display.print_error(cli.describe_error(error))
    return EXIT_FAILURE

if __name__ == "__main__":
    sys.exit(main())