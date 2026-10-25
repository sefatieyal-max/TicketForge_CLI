# TicketForge CLI

A terminal client for [TicketForge](https://integrations-assignment-ticketforge.vercel.app).
It lets you set up a connection, then list, show, create and update tickets,
either through an interactive menu or with one-line commands.

TicketForge has no public API documentation, so the API was reverse engineered
from the web app (see [How the API was discovered](#how-the-api-was-discovered)).

## Requirements

- Python 3.10+ (uses `match`/`case`); developed and tested on Python 3.14, Windows 11
- Packages in `requirements.txt`: `requests`, `keyring` (secure password storage),
  `colorama` (colors on Windows), `pytest` + `responses` (tests)

## Installation

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Setup

```bash
python main.py setup
```

Setup asks for the server URL (Enter keeps the default), username and password
(hidden), offers to register a new account, **verifies the credentials against the
API**, and only then saves the settings.

- `~/.ticketforge/config.json` stores only the URL and username, never the password.
- The password is read from, in order: the `TICKETFORGE_PASSWORD` environment variable,
  the OS credential store (Windows Credential Manager / macOS Keychain, via `keyring`,
  if you chose to save it), or a hidden prompt.

## Usage

### Interactive menu

```bash
python main.py
```

```
=== TicketForge ===
Logged in as eyal | API requests left: 49/50
  1. List my tickets
  2. Show a ticket
  3. Create a ticket
  4. Update a ticket
  5. Switch user
  6. Log out (forget saved password) and exit
  0. Exit
```

The password is checked once when the menu starts (a wrong one can be re-typed up
to 3 times, or you can switch user). Errors and Ctrl+C inside an action return to
the menu; Ctrl+C at the menu exits.

### Commands

| Command | What it does |
|---|---|
| `python main.py setup` | Configure and verify the connection |
| `python main.py list [--limit N] [--all]` | List your tickets, N per page (Enter = next page) |
| `python main.py show REF` | Show one ticket |
| `python main.py create [--title T] [--description D] [--depends-on REFS]` | Create a ticket (asks for anything missing) |
| `python main.py update REF [--title] [--description] [--stage] [--depends-on]` | Update a ticket (interactive if no options) |
| `python main.py --help` / `python main.py update --help` | Help |

A ref can be written as `TF-12`, `tf-12`, `#12` or just `12`.
Stages: `open`, `in_progress`, `review`, `closed` (`"In Progress"` also works).

### Examples

```
$ python main.py list --limit 2
REF       STAGE         TITLE                                     UPDATED
----------------------------------------------------------------------------------
TF-578    open          test                                      2026-10-25 10:34
TF-577    open          6                                         2026-10-25 10:20
-- Enter for more, q to stop: q

Showed 2 ticket(s). More are available (use --all to list everything).
API requests left: 48/50

$ python main.py create --title "From CLI" --description "created with args" --depends-on 578
[ok] Created TF-580: From CLI

$ python main.py update 580 --stage review
Changes:
  stage: open  ->  review
Save these changes to TF-580? [y/n]: y
[ok] Updated TF-580.

$ python main.py show 99999
[!] Ticket TF-99999 was not found.

$ python main.py list --limit abc
ticketforge list: error: argument --limit: must be a whole number between 1 and 50
```

## How the API was discovered

1. **Network tab** (Chrome DevTools, Fetch/XHR filter, Preserve log): performed every
   action in the web app and recorded the method, URL, payload and response of each call.
2. **Sources tab search** (Ctrl+Shift+F in the site's own JS bundles): found things that
   no response shows, such as the allowed `stage` values, the cursor pagination logic,
   and endpoints not reachable through clicks.
3. **curl / Python one-liners** to confirm behaviour before coding it (for example, what
   a missing ticket returns).

### API map

Base URL: `https://integrations-assignment-ticketforge.vercel.app/api/tforge`

| Action | Request | Body | Response |
|---|---|---|---|
| Register | `POST /user/register` (no auth) | `{username, password}` | `{user: {...}}` |
| My tickets | `GET /workitems/mine?limit=5&cursor=...` | | `{workitems: [...], pagination: {limit, hasMore, nextCursor}}` |
| One ticket | `GET /workitem/{ref}?view=deep` | | `{workitem: {..., owner, dependsOn, customFields}}` |
| Create | `POST /workitem/publish` | `{title, description, dependsOn, customFields?}` | `{workitem: {...}}` |
| Update | `PUT /workitem/{ref}` | **all fields**: `{title, description, stage, dependsOn, customFields}` | `{workitem: {...}}` |
| Custom fields | `GET /custom-fields`, `POST /custom-fields`, `PUT/DELETE /custom-fields/{id}` | | |

### Findings and quirks

- **Auth is HTTP Basic** (`Authorization: Basic base64(user:pass)`) on every request.
  There is no login endpoint: the web app "logs in" by calling `GET /workitems/mine`
  and checking for 401. The CLI does the same (`verify_credentials`).
- **A missing ticket returns `400`, not `404`**, with body
  `{"err": "not_found", "message": "...", "retryable": false}`. The client checks the
  `err` code before the status code, so the user still gets a "not found" message.
- **Update is a full replace (`PUT`).** Sending only `{stage}` would risk wiping other
  fields, so the CLI fetches the ticket fresh, applies only the requested changes,
  shows a preview, asks for confirmation, then sends every field.
- **Rate limit: 50 requests per ~60 s window**, reported in `X-RateLimit-Limit`,
  `X-RateLimit-Remaining` and `X-RateLimit-Reset` (an **ISO timestamp**, not seconds).
  Error responses don't carry these headers.
- A `:` in a username would break Basic auth, so usernames with `:` are rejected locally.
- **Non-ASCII titles** (e.g. Hebrew) crashed when output was redirected to a file on
  Windows (cp1252). `main()` now forces UTF-8 on stdout/stderr.

## Project structure

| File | Responsibility |
|---|---|
| `main.py` | Entry point: argparse commands, dispatch, the single top-level error handler |
| `cli.py` | User flow for each feature: what to ask, when to call the API, what to show |
| `client.py` | **All HTTP.** Auth, error mapping, pagination, rate-limit tracking. Never prints or asks |
| `exceptions.py` | Error hierarchy (`AuthError`, `NotFoundError`, `RateLimitError`, ...) |
| `validators.py` | Pure input parsers: return the normalized value or `None` |
| `prompts.py` | Generic input helpers: ask, re-ask until valid, confirm, hidden password |
| `display.py` | **All formatting and printing:** tables, colors, dates, menu, change preview |
| `config.py` | Saved settings and password storage (env var / keyring) |
| `tests/` | pytest suite, no network |

## Design decisions

- **Layered, one job per module.** The CLI never imports `requests`; the client never
  prints. Swapping the HTTP library or the UI touches one file.
- **Custom exceptions** turn HTTP details into meaning (`NotFoundError` vs a raw 400),
  so the CLI can react and show a friendly message. No traceback reaches the user.
- **Menu and commands share the same methods.** Both call `TicketForgeCLI.update_ticket`
  etc.; only the input source differs. Validation rules live once in `validators.py`
  and are adapted to argparse (`validated()` in `main.py`) and to `input()` (`prompts.py`).
- **Validate locally, let the API decide the rest.** Certainly-invalid input (bad ref,
  unknown stage) costs zero requests. Refs are also URL-encoded as a second safety layer.
- **Pagination is cursor-based and on demand.** One page per request; the user decides
  whether to load more (`--all` fetches everything).
- **Request cost:** list = 1 per page, show = 1 (+1 only if the ticket has custom fields),
  create = 1, update = 2 (fresh read + PUT), menu start = 1 (password check).
- **Rate limits:** remaining budget is read from response headers and shown in the menu;
  a 429 becomes `RateLimitError` with the wait time when known.
- **Secrets:** password never written to disk in plain text and never printed.
- **Dependency injection:** `TicketForgeCLI(client)` receives its client, so tests use a fake.

## Tests

```bash
python -m pytest -v
```

63 tests, no network (HTTP is faked with `responses`, the CLI gets a fake client,
config uses a temp folder). They cover validators (including boundaries), status →
exception mapping (including the 400/not_found quirk, 429, HTML bodies, timeouts),
cursor pagination, the full-field PUT payload, the update flow (unchanged fields kept,
nothing sent on "n" or no changes), setup, login retries, switch user and logout.

## Assumptions and limitations

- Only **your own** tickets are listed (`/workitems/mine`); the app exposes no "all tickets" endpoint.
- Custom fields are shown on tickets and the API methods exist in the client, but editing
  custom field values from the CLI is not implemented yet.
- **Race condition:** between the fresh read and the `PUT`, someone else could change the
  ticket; their change would be overwritten. The API offers no version/ETag to prevent it.
- Clearing a description from the command line isn't supported (PowerShell drops `""`);
  use the interactive update and type `-`.
- No automatic retry on 429: the user is told how long to wait. The API's `retryable`
  flag could drive automatic retries in the future.
- Field length limits are left to the API to enforce.

## Evidence

See `evidence/` for screenshots / recorded terminal output of each command.

## AI Disclosure

I used Claude (Anthropic) as a pair programmer. It drafted most of the code and
the initial module layout, read the web app's JS bundles to map the API, and
drafted the tests and this README.

My role was to direct, review and verify:
* **Code review and refactoring:** I reviewed every change before applying it by
  hand, questioned design choices, and pushed refactors where separation of
  concerns was broken (menu and change-preview printing moved into `display.py`,
  input helpers extracted into `prompts.py`, title formatting made reusable).
* **Product decisions:** I defined the UX behaviours: an interactive menu on top
  of the commands, showing the current user and remaining API budget, staying on
  a login prompt after a wrong password, and switching user from there.
* **API investigation and verification:** I inspected the app with DevTools
  (Network and Sources search) and verified behaviour with curl before coding it,
  which revealed that a missing ticket returns 400 with `err: not_found` instead
  of 404.
* **Testing against the live system:** I ran every step against the real
  TicketForge API, found and reported bugs (e.g. update prompting interactively
  despite `--stage`, Ctrl+C messaging), and confirmed the fixes.
