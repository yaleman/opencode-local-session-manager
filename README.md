# opencode-local-session-manager

A local web UI for browsing [OpenCode](https://github.com/opencode-ai/opencode) sessions. It reads the OpenCode SQLite database and serves a Flask app that lets you search, filter, and inspect your session history in the browser.

## Features

- Paginated session list with search by title
- Filter by project and archived/active/all status
- Session detail view with full conversation (messages, tool calls, file patches)
- Cost, token count, and timing metadata per session
- Dark-themed UI

## Requirements

- [uv](https://github.com/astral-sh/uv)
- Python 3.12+

## Usage

```bash
uv sync
uv run python opencode-local-session-manager.py
```

Then open <http://localhost:5173>.

The app reads from `~/.local/share/opencode/opencode.db` by default.

## Development

```bash
uv run pytest
```
