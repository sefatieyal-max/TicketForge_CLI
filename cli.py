"""User flow for each command: ask, validate, call the client, print.

The CLI receives its client from outside (dependency injection), so tests
can pass a fake client. It never builds URLs and never formats tables.
"""

import config
import display
import validators
from client import DEFAULT_BASE_URL, DEFAULT_PAGE_SIZE, TicketForgeClient
from exceptions import AuthError, NotFoundError, RateLimitError, TicketForgeError
from prompts import ask, ask_password, ask_valid, confirm



LOAD_MORE_KEY = ""
CLEAR_VALUE = "-"
STAGE_EXAMPLE = ", ".join(validators.STAGES)
REF_EXAMPLE = "TF-12 or just 12"
EXIT_CHOICE = "0"
LOGOUT_CHOICE = "6"
MAX_LOGIN_ATTEMPTS = 3
MENU_TITLE = "TicketForge"




# ---------- setup (runs before a config exists) ----------

def run_setup():
    """Ask for connection details, verify them, save them. Returns True on success."""
    base_url = ask(f"TicketForge URL [{DEFAULT_BASE_URL}]: ") or DEFAULT_BASE_URL
    username = ask_valid("Username: ", validators.parse_username, "Eyal (no ':' allowed)")
    if username is None:
        print("Setup cancelled.")
        return None
    password = ask_password()
    if password is None:
        print("Setup cancelled.")
        return None

    client = TicketForgeClient(username, password, base_url=base_url)
    if not confirm("Do you already have a TicketForge account?"):
        client.register(username, password)
        display.print_success(f"Account '{username}' created.")
    client.verify_credentials()           # raises AuthError if wrong

    path = config.save_config(base_url, username)
    display.print_success(f"Connected as '{username}'. Settings saved to {path}")
    _offer_to_store_password(username, password)
    return client


def _offer_to_store_password(username, password):
    if not confirm("Save the password in your OS credential store?"):
        print(f"OK. Set {config.PASSWORD_ENV} or you will be asked each time.")
        return
    if config.store_password(username, password):
        display.print_success("Password saved securely.")
    else:
        display.print_error(f"Could not save it (is 'keyring' installed?). Use {config.PASSWORD_ENV}.")


def build_client():
    """Client from the saved config. Raises ConfigError if setup was never run."""
    settings = config.load_config()
    username = settings["username"]
    password = config.read_saved_password(username) or ask_password(f"Password for {username}: ")
    return TicketForgeClient(username, password, base_url=settings["base_url"])

def describe_error(error):
    """One friendly line for any of our exceptions (used by main.py and the menu)."""
    if isinstance(error, AuthError):
        return f"{error} Run 'python main.py setup' to fix your credentials."
    if isinstance(error, RateLimitError) and error.wait_seconds is not None:
        return f"{error} Try again in {error.wait_seconds} seconds."
    return str(error)
# ---------- commands that need a configured client ----------

class TicketForgeCLI:
    """One method per command. Receives the client so tests can inject a fake."""

    def __init__(self, client):
        self.client = client

    def list_tickets(self, page_size, show_all=False):
        """Show tickets page by page (cursor pagination). Enter = next page, q = stop."""
        cursor = None
        shown = 0
        while True:
            tickets, cursor = self.client.list_tickets_page(cursor=cursor, limit=page_size)
            if shown == 0 and not tickets:
                print("You have no tickets yet. Create one with: python main.py create")
                return
            if shown == 0:
                display.print_ticket_table(tickets)
            else:
                self._print_rows(tickets)
            shown += len(tickets)
            if cursor is None:
                print(f"\n{shown} ticket(s).")
                break
            if not show_all and not self._wants_more():
                print(f"\nShowed {shown} ticket(s). More are available (use --all to list everything).")
                break
        display.print_info(display.format_rate_limit(self.client.rate_remaining, self.client.rate_limit))

    def show_ticket(self, ref):
        """Print one ticket with all its details."""
        ticket = self._fetch_ticket(ref)
        display.print_ticket_details(ticket, self._field_labels(ticket))

    def create_ticket(self, title=None, description=None, depends_on=None):
        """Create a ticket. Asks only for the fields that were not given."""
        if title is None:
            title = ask_valid("Title (Enter to cancel): ", validators.parse_title, "Fix login bug")
            if title is None:
                print("Cancelled. Nothing was created.")
                return
        if description is None:
            description = ask("Description (optional): ")
        if depends_on is None:
            depends_on = ask_valid("Depends on (comma-separated refs, optional): ",
                                   validators.parse_ref_list, "TF-1, TF-2")
        ticket = self.client.create_ticket(title, description, depends_on)
        display.print_success(f"Created {ticket.get('ref')}: {ticket.get('title')}")

    def update_ticket(self, ref, changes=None):
        """Change a ticket. The API replaces the whole ticket (PUT), so: fetch it
        fresh, apply only the requested changes, preview, confirm, then send."""
        current = self._fetch_ticket(ref)
        before = self._editable_fields(current)
        after = {**before, **(changes or self._ask_changes(current))}
        if after == before:
            print("No changes. Nothing was sent.")
            return
        display.print_changes(before, after)
        if not confirm(f"Save these changes to {ref}?"):
            print("Cancelled. Nothing was changed.")
            return
        self.client.update_ticket(ref, **after)
        display.print_success(f"Updated {ref}.")

    @staticmethod
    def _editable_fields(ticket):
        """Everything the PUT endpoint expects, taken from the current ticket."""
        return {
            "title": ticket.get("title"),
            "description": ticket.get("description"),
            "stage": ticket.get("stage"),
            "depends_on": ticket.get("dependsOn") or None,
            "custom_fields": ticket.get("customFields") or {},
        }

    def _ask_changes(self, ticket):
        """Interactive edit. Enter keeps a value; returns only what changed."""
        print(f"Editing {ticket.get('ref')}. Press Enter to keep the current value.")
        changes = {}
        title = ask_valid(f"Title [{ticket.get('title')}]: ", validators.parse_title, "Fix login bug")
        if title:
            changes["title"] = title
        stage = ask_valid(f"Stage [{ticket.get('stage')}] ({STAGE_EXAMPLE}): ",
                          validators.parse_stage, STAGE_EXAMPLE)
        if stage:
            changes["stage"] = stage
        description = ask(f"Description [{ticket.get('description') or '-'}] ('{CLEAR_VALUE}' to clear): ")
        if description:
            changes["description"] = None if description == CLEAR_VALUE else description
        return changes



    def run_menu(self):
        """Numbered menu loop. Every action runs inside one safety net."""
        menu = {
            "1": ("List my tickets", lambda: self.list_tickets(DEFAULT_PAGE_SIZE)),
            "2": ("Show a ticket", lambda: self._with_ref(self.show_ticket)),
            "3": ("Create a ticket", self.create_ticket),
            "4": ("Update a ticket", lambda: self._with_ref(self.update_ticket)),
            "5": ("Switch user", self.switch_user),
            LOGOUT_CHOICE: ("Log out (forget saved password) and exit", self.logout),
        }
        if not self._login():
            return False
        while True:
            status = display.format_status(self.client.username, self.client.rate_remaining, self.client.rate_limit)
            display.print_menu(MENU_TITLE, {key: label for key, (label, _) in menu.items()}, EXIT_CHOICE, status)
            choice = input("Choose: ").strip()
            if choice == EXIT_CHOICE:
                print("Goodbye!")
                return True
            if choice not in menu:
                display.print_error(f"Please choose one of: {', '.join(menu)} or {EXIT_CHOICE}.")
                continue
            self._run_safely(menu[choice][1])

            if choice == LOGOUT_CHOICE:
                return True

    def _login(self):
        """Check the password before showing the menu (1 request, also reads the budget).
        On a wrong password, ask again, up to MAX_LOGIN_ATTEMPTS in total."""
        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            try:
                self.client.verify_credentials()
                return True
            except AuthError:
                display.print_error("Invalid username or password.")
            if attempt == MAX_LOGIN_ATTEMPTS:
                break
            if confirm("Log in as a different user?"):
                return self.switch_user()
            password = ask_password(f"Password for {self.client.username} (Enter to quit): ")
            if password is None:
                return False
            self.client.set_password(password)
        display.print_error("Too many failed attempts. Run 'python main.py setup' if you forgot the password.")
        return False

    def switch_user(self):
        """Run setup again and continue the session as the new user. Returns True on success."""
        new_client = run_setup()
        if new_client is None:
            return False
        self.client = new_client
        return True


    def logout(self):
        """Forget the saved password for the current user."""
        if config.delete_password(self.client.username):
            display.print_success(f"Saved password for '{self.client.username}' removed.")
        else:
            print("No saved password to remove.")
        print("Logged out. Next time you will be asked for the password (or run setup).")


    @staticmethod
    def _run_safely(action):
        """Run one menu action. On an error, show it and return to the menu."""
        try:
            action()
        except KeyboardInterrupt:
            print("\nCancelled. Back to the menu.")
        except TicketForgeError as error:
            display.print_error(describe_error(error))

    @staticmethod
    def _with_ref(action):
        """Ask for a ticket ref, then run `action(ref)`. Enter goes back."""
        ref = ask_valid(f"Ticket ref ({REF_EXAMPLE}, Enter to go back): ", validators.parse_ref, REF_EXAMPLE)
        if ref:
            action(ref)

    def _fetch_ticket(self, ref):
        """Fresh copy of a ticket, or None (with a friendly message) if it doesn't exist."""
        try:
            return self.client.get_ticket(ref)
        except NotFoundError:
            raise NotFoundError(f"Ticket {ref} was not found.") from None

    def _field_labels(self, ticket):
        """Custom field labels, fetched only when the ticket has custom fields (saves a request)."""
        if not ticket.get("customFields"):
            return {}
        return {field.get("name"): field.get("label") for field in self.client.list_custom_fields()}

    @staticmethod
    def _print_rows(tickets):
        for ticket in tickets:
            print(display.format_ticket_row(ticket))

    @staticmethod
    def _wants_more():
        answer = input("-- Enter for more, q to stop: ").strip().lower()
        return answer == LOAD_MORE_KEY