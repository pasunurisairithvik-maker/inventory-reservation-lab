# OrderOps hosted demo
Standalone public portfolio demonstration of stock reservations, order state transitions, and event recovery. The primary Python application remains at https://github.com/pasunurisairithvik-maker/inventory-reservation-lab.

## Runtime
The hosted edition runs on a Worker-compatible JavaScript/TypeScript backend and D1. It is not a remote Python server. Each visitor receives an opaque HttpOnly SameSite session cookie identifying a separate fictional workspace. Workspaces persist on the server; localStorage is not authoritative.

Each bounded workspace is one versioned JSON state record. A prepared conditional UPDATE compares its version and commits the entire order, stock, audit, and outbox mutation atomically. Concurrent versions retry up to ten times. This deliberately small model caps each workspace at 100 orders, stock receipts at 1000 units per action, and successful mutations at 60 per minute. It is not a scalable database design for a real store.

Automatic delivery is request-driven: page refreshes process ready events and overdue holds. Closing the page leaves queued state saved; processing resumes on a subsequent request. No always-on scheduled worker or external message delivery is claimed. The Python edition runs an independent background worker when launched.

## Verification
- `node tests/domain.test.mjs`: 13 domain checks.
- `node node_modules/typescript/bin/tsc --noEmit`: type checking.
- `python tests/integration.py`: actual local-preview HTTP concurrency, workspace isolation, idempotency, and cross-origin rejection. Requires the supervised preview and its local D1 migration.
- `results/hosted-integration.json`: 50 concurrent API requests using eight clients against eight units; eight accepted and 42 stock conflicts, with balanced inventory.
- Browser QA: create, confirm, reload persistence, and both lab simulations checked through the supported preview.

The hosted lab is a deterministic state-machine simulation. It is labelled as such and does not claim the Python concurrent workload was executed by a browser button.

## Independence and boundaries
Source, schema, migrations, tests, and the dashboard are kept with the project. Deployment does not depend on an active chat or a developer laptop. Visitors need no ChatGPT account. No plugins, OpenAI keys, external connectors, payment integrations, or customer credentials are used.

This is an anonymous demo, not account-based production software. Use fictional aliases only. Clearing the session cookie or choosing Start fresh demo makes a new workspace. Demo data should not be treated as personal business records. Backend storage is managed by the host; moving providers requires deploying the runtime and migrating its database, not merely copying an HTML file.

Initial implementation is AI-assisted; no production customers, research novelty, or hiring outcome claimed.
