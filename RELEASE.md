# Release 1.0 — OrderOps inventory and delivery simulator

This is a completed release within the scope below. Version 1.0 does not imply public-service readiness, unlimited traffic, security certification or an uptime guarantee.

## Supported use
OrderOps inventory and delivery simulator. Start commands and examples are in [README.md](README.md). Use Python 3.11 or newer in a clean virtual environment with the pinned requirements. Browser interfaces are available where documented; the health probe is a command-line tool.

## Verification
43 Python tests (6 require isolated PostgreSQL) and a JavaScript domain suite. Run `python -m unittest discover -s tests -v` from this repository. A green result with skipped PostgreSQL tests does not count as PostgreSQL verification; use the isolated database job in CI for that coverage. Never run destructive test fixtures against an operational database.

## Storage and recovery
Local INVENTORY_DB or dedicated PostgreSQL DATABASE_URL. Retry an interrupted request with its original key. Never alter stock to conceal failure. Token fencing and receiver deduplication recover interrupted delivery.

For a SQLite database, use Python's `sqlite3.Connection.backup()` to an independent destination rather than copying an open database file. Restore only while all writers are stopped, keep the current database as a fallback, and test the restored copy before replacing it. For PostgreSQL, use a dedicated role and the provider's documented export/restore process. Never commit database copies, tokens, passwords, real customer records or uploaded files.

## Operating boundaries
Use fictional data only. Anonymous public workspaces are not customer accounts. No payments, shipping or external messaging. Free hosting sleeps and workspace capacity is bounded.

## Change control
Run the full tests before publishing a change. Keep existing measurements and attribution. A benchmark rerun is a new observation, not permission to replace an unfavorable result. Store secrets in environment variables. Roll back to a known working commit only after checking compatibility with any schema changes; do not force push or erase newer unrelated work.

## Security reports
Never put credentials, private datasets or customer receipts in public issues. A sanitized issue can describe the affected version, expected behavior and a minimal synthetic reproduction. No independent security audit is claimed.
