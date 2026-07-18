<p align="center">
  <img src="./images/logo.png" alt="DataClever AI" width="920">
</p>

# pdf-tree

PDF tree builder using docling. Architecture designed by Jonathan Potes, CTO.

## Setup

```bash
uv sync --all-extras --dev
npm install
npm run prepare   # activates the husky hook (commitlint)
```

## Running the app

```bash
uv run streamlit run streamlit_app/app.py
```

## Project structure

- `src/models/` — data models (extraction results, etc.)
- `src/pipeline/` — main processing pipeline
- `src/tree_builder/` — TOC/bookmark extraction, section matching, tree export
- `src/validation/` — tree validation and coverage checks
- `streamlit_app/` — UI (pages, components, services)
- `tests/unit/` — unit tests

## CI/CD

- **Lint + tests in CI** (ruff + pytest via uv) on every PR and push to `main`.
- **Conventional Commits enforced** — validated locally (husky) and in CI.
  Use `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, etc.
- **Automatic changelog and releases** via release-please, following
  Keep a Changelog sections (Added/Changed/Fixed).
- **Proprietary license** — see `LICENSE.md`.
