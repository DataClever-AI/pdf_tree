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

For durable QA reviews, set `PDF_TREE_SOURCE_DIR` to the local PDF folder and
`PDF_TREE_QA_DIR` to the versioned evidence folder. Both can also be changed in
the Streamlit sidebar. Qwen3-VL uses `QWEN3_VL_URL`, `QWEN3_VL_MODEL`, and
`QWEN3_VL_TOKEN` from `.env` or `st.secrets`; the URL must end in
`/v1/chat/completions`.

## Project structure

- `src/models/` — data models (extraction results, etc.)
- `src/pipeline/` — main processing pipeline
- `src/tree_builder/` — TOC/bookmark extraction, section matching, tree export
- `src/validation/` — tree validation and coverage checks
- `src/qa_workflow/` — versioning, sampling, AI drafts, human review, confidence reports
- `streamlit_app/` — UI (pages, components, services)
- `tests/unit/` — unit tests
- `tests/qa_workflow/` — QA workflow unit and integration tests

## CI/CD

- **Lint + tests in CI** (ruff + pytest via uv) on every PR and push to `main`.
- **Conventional Commits enforced** — validated locally (husky) and in CI.
  Use `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, etc.
- **Automatic changelog and releases** via release-please, following
  Keep a Changelog sections (Added/Changed/Fixed).
- **Proprietary license** — see `LICENSE.md`.
