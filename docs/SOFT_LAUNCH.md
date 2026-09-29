# OrderOps soft launch

Live demo: https://orderops-rithvik.nehapasunuru0156.chatgpt.site

Published 29 September 2026. This public demo runs independently of ChatGPT and the student's laptop. No login is required. Use fictional names only; there are no real payments, messages, or customers.

## Try it
Create an order, confirm or cancel it, then inspect stock and event delivery. Reload to recover the same browser's workspace. Fresh demo starts another workspace. Each visitor has a separate database workspace selected by an opaque HttpOnly cookie. Cookie loss or expiry removes access to the old workspace; this is not account storage.

## Independent implementations
- Python: FastAPI and SQLite. `python launch.py` starts the API and continuous local worker. Thirty tests cover domain behavior and API integration. The real threaded experiment accepted 10 of 50 requests against 10 units.
- Hosted: JavaScript/TypeScript Worker and D1. Conditional version updates atomically commit each workspace. Thirteen domain checks and local hosted API tests cover retries, isolation, and contention. Fifty competing API requests accepted exactly 8 orders against 8 units, leaving zero stock. Reference source/results are in hosted-reference; full hosted source is also in the download.

Hosted delivery and expiry are request-driven: page refreshes process ready events, and processing resumes on the next request after browsers close. There is no always-running hosted scheduler. Hosted browser lab examples are deterministic simulations; they are distinct from the actual concurrency tests.

## Boundaries
The demo limits each workspace to 100 orders and bounds inputs and successful mutation frequency. There is no production authentication, real commerce, uptime SLA, or claim of large-scale performance. Publication was confirmed by deployment status; browser and API checks ran against the internal preview. Full source permits independent learning and adaptation, although the hosted build requires compatible Worker/D1 infrastructure.

The implementation is AI-assisted. The student should reproduce the experiments, understand the code, and describe their own contributions honestly.

## Zero-budget Python migration
The external Python deployment now uses Render Free and Neon Free PostgreSQL; no paid disk is configured. See deploy/RENDER.md. It has not yet been provisioned. PostgreSQL uses relational per-workspace schemas and a real Python worker, which pauses when the free web host sleeps. The previous TypeScript live demo and its measured results remain accurately attributed above.
