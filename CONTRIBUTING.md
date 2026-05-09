# Contributing

Thanks for your interest in `mapy-com-mcp`. This file is the 60-second
orientation; [AGENTS.md](AGENTS.md) is the source of truth for repo standards
and workflow.

## Setup

```sh
uv sync
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

The second `pre-commit install` is required — it wires up the Conventional
Commits check on commit messages.

## Run, test, lint

```sh
uv run mapy-com-mcp   # run the server (stdio)
make test             # run pytest
make lint             # run pre-commit across all files
```

## Branching and commits

- Feature branch off `main`, named `<type>/<kebab-description>`
  (`feat/...`, `fix/...`, `chore/...`, `docs/...`, `refactor/...`, `test/...`,
  `ci/...`).
- [Conventional Commits](https://www.conventionalcommits.org/) for every
  commit message — enforced by the `commit-msg` hook above.
- Don't force-push `main`. Don't skip hooks (`--no-verify`). Fix the cause,
  not the symptom.

## Pull requests

- Target `main`. PR title in Conventional Commits format.
- Description: short *why*, bulleted summary of changes, test-plan checklist
  (the PR template covers this).
- One logical change per PR.

For the longer rationale behind any of the above, see
[AGENTS.md](AGENTS.md).
