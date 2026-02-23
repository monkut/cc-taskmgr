# Tony - GitHub Issue Manager

A terminal UI (TUI) for managing GitHub issues assigned to you, built with [Textual](https://textual.textualize.io/).

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/guides/install-python/) for dependency management
- [GitHub CLI](https://cli.github.com/) (`gh`) authenticated via `gh auth login`
- (Optional) [askcc](https://github.com/kiconiaworks/askcc-cli) for executing agent actions on issues

## Installation

```bash
git clone https://github.com/kiconiaworks/cc-taskmgr.git
cd cc-taskmgr
uv sync
```

Install pre-commit hooks (ruff lint/format):

```bash
pre-commit install
```

## Usage

```bash
uv run tony
```

On first launch, Tony prompts for your GitHub username and (optionally) local project directories. Configuration is stored at `~/.config/cc-task-manager/config.toml`.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Cycle focus: Org filter → Project filter → Column headers → Issue rows |
| `Enter` | Open selected issue (row focus) / Toggle sort (column header focus) |
| `Up` / `Down` | Navigate issue list |
| `r` | Refresh issues |
| `s` | Open settings |
| `Escape` | Back to issue list (from detail view) |
| `q` | Quit |

### Filtering

Use the **Org** and **Project** dropdowns in the filter bar to narrow issues by organization or GitHub Project V2.

### Issue Detail

Select an issue and press `Enter` to view details including body, labels, and comments. From the detail view you can:

- **Post a comment** via the comment input
- **Execute Action** — launches an `askcc` agent mode (`plan`, `develop`, `review`, `explore`, `diagnose`) against the issue. Requires `askcc` on PATH and a matching local project directory configured in Settings.

## Project Structure

```
tony/
├── app.py              # Main TonyApp entry point
├── app.tcss            # Textual CSS styles
├── config.py           # AppConfig (TOML persistence)
├── github.py           # GitHub CLI wrapper (fetch issues, projects, labels)
├── models.py           # Issue, Comment, Label, Project dataclasses
├── functions.py        # Utility functions
├── screens/
│   ├── settings.py     # Settings modal (username, project dirs)
│   ├── action_select.py    # askcc mode selection modal
│   └── confirm_action.py   # Action confirmation modal
└── widgets/
    ├── filters.py      # Org/Project filter bar
    ├── issue_table.py  # Sortable issue DataTable
    └── issue_detail.py # Issue detail view with comments
```

## Development

### Code checks

```bash
uv run poe check       # ruff lint
uv run poe typecheck   # pyright
```

### Tests

```bash
uv run poe test
```

### Build

```bash
uv build
```

## CI

GitHub Actions runs lint, tests, and (on `main`) builds and publishes a GitHub Release. See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
