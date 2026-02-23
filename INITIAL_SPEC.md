# ISSUE MANAGER

A terminal UI (Textual TUI) application that tracks OPEN GitHub issues assigned to a configured user across all repos and orgs.

## Technology Stack

- **UI**: [Textual](https://textual.textualize.io/) TUI framework
- **Data**: GitHub CLI (`gh`) for all API access
- **Language**: Python 3.14+
- **Packaging**: uv with pyproject.toml
- **Testing**: pytest

## Data Model

### Source

All data is fetched via `gh search issues --assignee=USER --state=open --json` with fields: `repository`, `title`, `number`, `url`, `labels`, `updatedAt`, `body`, `comments`.

Orgs and repos are derived from the returned issues (no separate configuration).

### Caching

- Issues are fetched on startup and on manual refresh
- No persistent local cache in Phase 1
- Pagination: fetch all open issues (gh handles pagination via `--limit`)

## Screens & Interactions

### Settings

Accessed via a gear icon / keybinding. Configures:

- **GitHub username**: the assignee to filter issues for

Settings are persisted to a local config file (`~/.config/cc-task-manager/config.toml`).

### Issue List (main view)

Displays all OPEN issues assigned to the configured user.

**Columns**: Org, Repo, Issue #, Title, Labels, Updated

**Default sort**: Most recently updated first.

#### Filters (cascading)

- **Organization**: ALL (default), or a specific org — derived from fetched issues
- **Repository**: ALL (default), or a specific repo — list narrows when an org is selected

Selecting an org filters both the issue list and the repo dropdown. Selecting "ALL" org resets the repo filter.

### Issue Detail (panel or overlay)

Displayed when an issue is selected from the list.

Shows:
- Issue title, number, labels, state
- Full description (markdown rendered)
- Comments (chronological, markdown rendered)

**Actions**:
- Add a comment (text input, append-only, posted via `gh`)

## Phase 2: askcc-cli Integration

After Phase 1 is stable, the issue detail view will add actions to invoke [askcc-cli](https://github.com/monkut/askcc-cli) agent modes:

- **Modes**: plan, develop, review, explore, diagnose
- **Working directory**: resolved from local clone of the issue's repo (user configures clone root)
- **Invocation**: launches askcc subprocess with `--github-issue-url` pointing to the selected issue
- Results are fire-and-forget (work happens in the terminal session askcc spawns)

## Out of Scope (Phase 1)

- Issue creation, closing, or label management
- askcc-cli integration (Phase 2)
- Multi-user support
- Notifications or polling for updates
- Offline mode or persistent caching
- Editing or deleting comments

## Error Handling

- **No user configured**: prompt settings on first run
- **`gh` not authenticated**: display error with `gh auth login` instructions
- **Zero issues**: show empty state message
- **Network/API errors**: display inline error with retry option

## Open Questions

- Keybinding scheme (vim-style, emacs, or default Textual?)
- Should label colors from GitHub be mapped to terminal colors?
