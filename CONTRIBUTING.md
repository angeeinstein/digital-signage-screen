# Contributing

1. Set up the development environment as described in the README ("Development").
2. Make your change on a branch.
3. Run the checks before opening a pull request:

   ```bash
   ruff check . && pytest -q
   cd frontend && npx tsc -b && npx vitest run && npx vite build
   ```

Guidelines:

- **External APIs** go in `signage/providers/`, one module per service. Fetch
  functions take a `requests.Session` and return plain dicts. Parsing should
  be a separate function, tested against a recorded response in
  `tests/fixtures/`.
- **New settings** go in `DEFAULTS` and `SCHEMA` in `signage/config.py`, and in
  `Config` in `frontend/src/lib/types.ts`. Secrets also go in `SECRET_FIELDS`.
- **Display lists** use `AutoFitList`, so rows are never cut off. Give every
  table cell `min-width: 0` and an ellipsis.
- Shell scripts must stay LF and pass `shellcheck`.
