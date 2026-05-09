# AGENTS.md

Vendor-neutral instructions for AI coding agents working in this repo. If
you're a Claude Code session, `CLAUDE.md` is a symlink to this file —
everything below applies.

## Project at a glance

`mapy-com-mcp` is a Model Context Protocol (MCP) server that gives LLM clients
first-class access to mapy.com (Czech mapping service). Built in Python ≥ 3.12
with FastMCP. Distributed on PyPI and invoked via `uvx mapy-com-mcp`.

For the public pitch and quickstart, read `README.md`.

## Repo layout

```
src/mapy_com_mcp/
  __init__.py
  server.py          # FastMCP entry, main(), tool auto-registration
  mapy_client.py     # the only place that talks to mapy.com over HTTP
  tools/             # one file per MCP tool
tests/               # pytest, mocked HTTP via respx
```

Conventions tied to this layout:

- `src/` layout, not flat. Tests must import the installed package, not the
  working directory.
- One file per tool in `tools/`. Auto-registered in `server.py`.
- `mapy_client.py` is the only HTTP boundary. Tools never make raw `httpx`
  calls — auth, retries, and error mapping live in one place.
- `tests/` lives outside `src/`. Coverage targets `src/mapy_com_mcp`.

## Standards

- **Lint + format:** `ruff` (config in `pyproject.toml`).
- **Type checking:** `pyright` in strict mode. Type hints everywhere.
- **Pre-commit:** ruff + pyright + basic hygiene hooks must pass.
- **Tests:** `pytest` with `respx` for HTTP mocking. No real network in CI.
- **Conventional Commits.** See "Git workflow" below.
- **No AI attribution in commits or PRs.** No `Co-Authored-By: Claude`
  trailers, no "Generated with Claude Code" footers, no other AI metadata.
  This is a hard rule — see `.context/decisions.md`.
- **Dependencies kept minimal.** `fastmcp`, `httpx`, `pydantic` (transitive
  via fastmcp). Anything beyond these needs an entry in
  `.context/decisions.md`.

## Working principles

How to make changes — separate from *what tools* to use.

- **No over-engineering.** The smallest thing that solves the task. No
  premature abstractions, no helper for a one-shot call site, no error
  handling for cases that can't happen, no design for hypothetical future
  requirements. Three similar lines beat a premature abstraction.
- **Avoid special-case ladders.** Don't solve every edge case by adding
  another `if/else` — that's how the code rots. `if/else` is the right answer
  only when avoiding it would itself be over-engineering (e.g. a class
  hierarchy or strategy pattern for two cases). Otherwise push the special
  case into the data, the type, or the boundary so the main path stays
  straight.
- **No workarounds for blockers — fix the root cause.** When something fails,
  don't bypass it. No `--no-verify`, no broad `# type: ignore`, no
  `except: pass` to swallow exceptions, no commenting out a failing test, no
  hardcoding values to "make the test pass". Investigate the actual cause and
  fix that.
- **Pushback on tooling rules is welcome — talk to the user first.** If a
  ruff lint or pyright check seems wrong for this codebase, don't sprinkle
  `# noqa` / `# type: ignore` to silence it. Surface it: "this rule fires on
  X, here's why I think it's not useful here — should we disable it
  project-wide?" The output is a real decision recorded in `pyproject.toml`
  (and `.context/decisions.md` if the rationale is non-obvious), not inline
  suppressions scattered through the code.

## How to run things

```
uv sync                       # install deps + create .venv
uv run mapy-com-mcp               # run the server (stdio by default)
uv run pytest                 # run tests
uv run pytest --cov=src/mapy_com_mcp   # tests with coverage
pre-commit run --all-files    # lint + type-check everything
make inspect                  # MCP Inspector against the local dev server
make inspect-remote           # MCP Inspector against the published PyPI build
```

The `make inspect*` targets shell out to `npx @modelcontextprotocol/inspector`,
so they require Node.js / npx in addition to the Python toolchain. Everything
else above only needs `uv`.

## Git workflow

Explicit rules so agent-driven work doesn't pollute `main` or muddy history.

- **Branching.** Never commit directly to `main`. Every change goes on a
  feature branch off `main`. Naming: `<type>/<kebab-description>` where
  `<type>` is one of `feat`, `fix`, `chore`, `docs`, `refactor`, `test`,
  `ci`. Examples: `feat/ping-tool`, `chore/scaffold-pyproject`,
  `docs/agents-and-subagents`.
- **Commits.** Conventional Commits: `<type>(<scope>)?: <subject>`,
  imperative mood, lowercase subject, no trailing period, ≤72 chars on the
  subject line. Body wrapped at 72, used for the *why*, not the *what*.
  Examples: `feat(tools): add ping tool`,
  `chore: scaffold pyproject and src layout`.
- **No AI attribution** in commit messages or PR descriptions. (See
  Standards above.)
- **PRs.** Target `main`. Title in Conventional Commits format. Description
  has a short *why*, a bulleted summary of changes, and a test-plan
  checklist. Reference the related issue if any.
- **No force-push to `main`.** No `--no-verify`, `--no-gpg-sign`, or
  hook-skipping unless the user explicitly asks. Pre-commit failures get
  fixed, not bypassed.
- **One logical change per PR.** If a branch grows two unrelated changes,
  split it.
- **Agent commit policy.** Agents only create commits when the user asks.
  Never auto-commit, never auto-push. PRs are opened only on explicit
  request.

## Multi-agent workflow

This repo runs with two narrow Claude Code sub-agents alongside the main
agent. They are defined in `.claude/agents/`:

- **`test-agent`** — the only agent allowed to edit files in `tests/` or run
  `pytest`. Evaluates failures and decides whether they're real bugs (→
  feedback to main agent) or stale tests (→ updates the test).
- **`review-agent`** — read-only. Independent reviewer that checks the main
  agent's work for shortcuts, inconsistencies, standards violations, docs
  alignment, and accidentally-committed secrets.

### When the main agent finishes a unit of work that touches code

Before declaring "done", the main agent **must**:

1. **Invoke `test-agent`** (Agent tool, `subagent_type: test-agent`) with a
   brief that includes (a) what changed and (b) **testing hints** — your
   suggestions for what's worth testing in the new code (happy path, edge
   cases, failure modes, the boundary most likely to break). test-agent
   takes these as suggestions, exercises its own judgment, runs the suite,
   adds tests for new features, evaluates failures, and updates
   `tests/README.md` as part of its work. It returns either "green" or
   actionable feedback.
2. **Invoke `review-agent`** (`subagent_type: review-agent`) with the same
   brief. review-agent returns text feedback only.
3. **Surface review-agent's feedback to the user verbatim** (or summarized
   faithfully) and discuss it before applying anything. The main agent does
   not silently apply review-agent suggestions, and does not silently
   dismiss them. The user is the arbiter — for each `must_fix` /
   `should_fix` item, the main agent states its own take (agree / disagree
   / propose alternative) and waits for the user's call.
4. **Apply whatever the user agreed to.** If non-trivial code changed,
   re-invoke test-agent and review-agent as needed.

### Boundaries

- Only `test-agent` edits files under `tests/` or runs `pytest`.
- `review-agent` is read-only — it never edits files, never runs `pytest`,
  never runs commands that mutate state.
- The main agent does **not** modify tests directly, even to "make CI green".
  When a test fails, the main agent asks test-agent to evaluate it first.

### Skip rule

Doc-only changes (`README.md`, `.context/`, `AGENTS.md`, `CLAUDE.md`) don't
require test-agent. review-agent is still invoked for consistency/standards
review on substantive doc changes, and its feedback is still discussed with
the user.
