# Inventory Reservation Lab
**Problem:** two buyers can read the last available item before either updates stock. This project makes the stock decrement and reservation insertion one transaction, preventing overselling in a single-host SQLite application.

## Two concrete cases
- 50 concurrent requests compete for 10 units: exactly 10 are accepted and stock remains zero.
- A client retries the same request key: it gets the original reservation without deducting stock again. A changed SKU/quantity with the same key returns a conflict.

## Run (Python 3.11+)
```bash
python -m venv .venv
# Activate: Windows .venv\Scripts\activate; macOS/Linux source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python demo.py
python seed.py
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8004
```
Open http://127.0.0.1:8004/docs for the interactive API. Reserve BOOK-001, confirm or release by reservation ID, and inspect /inventory. seed.py intentionally refuses to overwrite existing stock; run once on a fresh database.

## State and correctness
Held reservations can be confirmed, released, or expired. Release/expiry restores stock once; confirmation consumes it permanently. `BEGIN IMMEDIATE` serializes SQLite writers. Conditional stock updates and database checks keep available stock nonnegative. Concurrent requests use separate connections. WAL permits readers alongside a writer; it does not create multiple simultaneous writers.

Expiry runs during service operations, not in a background scheduler. A rejected operation rolls its transaction back, including any expiry cleanup; the next successful operation or /inventory applies the expiry. Expired request keys remain bound to their original reservation. Reuse requires a new key. TTL is selected on first creation; retries cannot extend it.

## Evidence and limits
results/contention.json records one reproducible local workload, without invented throughput or latency. Tests cover contention, duplicate keys, terminal states, expiry, restart persistence and HTTP behavior. This is a learning project, not an Amazon-scale distributed inventory service. No payment integration, authentication, multi-item orders, background cleanup, or distributed database. Run locally only; public deployment requires access controls and operational design.

## Interview discussion
Explain why read-then-write without a transaction races, why retries need idempotency, and why SQLite is appropriate for this small demo. Discuss moving to PostgreSQL conditional updates and atomic multi-item reservations as future work, not implemented features.

AI-assisted initial implementation. STUDENT_GUIDE.md separates suggested student contributions from the generated baseline.
