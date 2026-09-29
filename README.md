# OrderOps — Order Reliability Control Room
A complete local Python application for managing inventory, multi-item order reservations, event delivery, and recovery. It expands the original inventory lab into one cohesive portfolio project.

**The problem:** stock checks, order creation, and event delivery fail in different ways. OrderOps keeps each reservation atomic and retains its delivery event even if a background worker stops.

## Start in one command
Python 3.11+ required. From this repository:
```bash
python launch.py
```
The launcher creates a project virtual environment, installs pinned application requirements from PyPI, seeds fictional examples, and serves the dashboard at **http://127.0.0.1:8004**. Initial setup needs internet access; application use does not. Ctrl+C stops the server. On Windows, use `py launch.py` if `python` is unavailable. It does not start an independent worker: use the dashboard's Process next event action or start the worker in a second terminal.

Manual setup:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.bootstrap
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8004
# Optional second terminal, with the virtual environment active:
python worker.py
```

## Four working views
| View | What you can do |
|---|---|
| Control room | Inspect actual inventory balance, order totals, reserved units, and stock receipts. |
| Orders | Reserve several products atomically, search/filter orders, confirm or cancel a hold. |
| Event delivery | Process local delivery, simulate a transient failure, inspect retries, and replay dead-letter events. |
| Reliability lab | Run isolated stock-contention and worker-crash experiments without affecting the store. |

## Two concrete demonstrations
**Limited stock:** 50 order requests use eight concurrent workers against ten units. Ten succeed, forty are rejected, and the stock ledger balances.

**Worker crash:** an event reaches the local inbox, then the worker loses its processing lease before acknowledging it. A replacement delivers again; the unique event ID leaves one inbox record, and the old worker cannot acknowledge the new claim.

Run `python verify_demo.py` to reproduce both, or use Reliability lab in the dashboard. See results/orderops-evidence.json. This is measured correctness on a small local workload, not a throughput or availability claim.

## Engineering substance
- Atomic multi-item reservations: if the second product is unavailable, the first product's decrement rolls back too.
- Idempotent order creation: a repeated request key returns the original order; a changed customer, item list, or TTL conflicts.
- Explicit order states: held → confirmed, cancelled, or expired. Cancellation/expiry returns stock once. Confirmed orders are final.
- Integer-paise arithmetic: no floating-point money calculations.
- Transactional outbox: order mutation, audit record, and delivery event commit together.
- Background worker: 15-second leases, fresh claim tokens, bounded retry backoff, and dead-letter replay.
- Idempotent local receiver: a unique event ID suppresses duplicate inbox effects after delivery-before-ack crashes.
- Inventory reconciliation: received = available + held + sold for every product.
- Responsive dashboard with search, status filters, accessible forms, and isolated failure experiments.

## Verify
```bash
python -m unittest discover -s tests -v
python verify_demo.py
```
Thirty tests currently cover domain correctness, concurrent buyers/workers, recovery, and API integration. The original ten inventory tests still pass. JavaScript syntax was checked separately. Automated browser interaction tests and visual verification are not included; do not infer full UI validation from backend CI. See docs/WALKTHROUGH.md and docs/ARCHITECTURE.md.

## Honest boundaries
Single-host SQLite, one local receiver, no external payment/email, no authentication, no user accounts, and no public deployment. UI lists return the latest 100 records; metrics count all stored records. Price totals are order value, not revenue. No shipping or refunds. Worker events are not guaranteed per-order delivery order; consumers should not treat the feed as an ordered state machine. Production deployment requires access controls, rate limits, migrations, monitoring, and a different concurrency/operations design.

The local receiver and order store share a database but delivery and acknowledgement use separate transactions to demonstrate the crash window. At-least-once delivery with a deduplicated local effect is not global exactly-once processing. Expiry runs during requests or worker cycles; no worker means no cleanup while the application is idle.

All seed products and aliases are fictional. Initial implementation is AI-assisted. No research novelty, customers, business impact, or independent student authorship is claimed. See STUDENT_GUIDE.md for concrete contributions the student can make and explain.

The original API and demo are preserved. Read docs/INVENTORY_LAB.md to run that smaller lab. Its tables are separate from OrderOps tables.
