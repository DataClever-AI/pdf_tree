<p align="center">
  <img src="./images/logo.png" alt="DataClever AI" width="920">
</p>

# pdf-tree

TODO: short project description.

## Setup

    uv sync --all-extras --dev
    npm install
    npm run prepare   # activates the husky hook (commitlint)

## What this template includes

- **Lint + tests in CI** (ruff + pytest via uv) on every PR and push to `main`.
- **Conventional Commits enforced** — validated locally (husky) and in CI.
  Use `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, etc.
- **Automatic changelog and releases** via release-please, following
  Keep a Changelog sections (Added/Changed/Fixed).
- **Proprietary license** — see LICENSE.md.

## Before using this repo for real

1. Replace `pdf-tree` in pyproject.toml, package.json, and
   release-please-config.json with the actual name.
2. Add this project's real logo at images/logo.png.
3. Branch protection on `main` is inherited automatically from the
   organization-wide ruleset — no extra setup needed.
