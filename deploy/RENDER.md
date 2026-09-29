# External Python deployment — Render

Status: deployment prepared; no Render account connected and no service provisioned yet. The previous chatgpt.site demo is a separate TypeScript edition. Do not claim that Render is live until deployment and public checks succeed.

## Reviewed deployment
`render.yaml` defines one 512 MB Python web service in Singapore, one 1 GB persistent disk, and deployment after main-branch checks pass. This is a paid configuration; approve current provider charges before provisioning. Free ephemeral disk hosting would lose this application's SQLite workspaces on restart.

Start command: `python serve.py --host 0.0.0.0`. Render supplies PORT. The supervisor starts the API and continuous Python worker and exits if either child dies, allowing the hosting platform to restart the service. SIGTERM stops both children. There is only one service/instance; do not run a separate worker against another disk or enable multiple Uvicorn processes.

## Account setup
Connect the Render plugin to an account you control. After costs are approved, import this repository's Blueprint, verify its plan/disk/region, and deploy. Render assigns the actual onrender.com URL; no particular hostname is guaranteed. No custom domain purchase is required. Never put provider credentials in the repository.

## Public mode
PUBLIC_DEMO=1 uses opaque 256-bit browser cookies and independent SQLite files under DEMO_WORKSPACES. HttpOnly and SameSite=Strict are always enabled; Secure is enabled on HTTPS. POST requests must originate from the same site. Legacy routes and API documentation are inaccessible publicly. Bodies are bounded to 12 KB. Workspaces have 100 orders, 60 mutation attempts per minute, and 1000 total mutation attempts. Idempotent retries remain valid at the order cap, subject to request quotas. There is a hard allocation cap of 250 workspaces with no automatic data deletion. Capacity exhaustion returns 503 and requires an operator decision; cookie loss creates another workspace. This is deliberately bounded anonymous portfolio hosting, not a scalable account system or abuse-proof multi-tenant service.

The worker traverses all workspace files and delivers local inbox events even with browsers closed. /healthz returns 503 if the worker heartbeat is absent or over 120 seconds old. A busy SQLite file is retried; this single-instance design does not provide an availability SLA. Persistent disk is not a substitute for a tested backup/restore procedure. Only fictional data should be entered.

## Acceptance checks after deployment
- Public HTTPS URL loads the Python dashboard; no ChatGPT login needed.
- Create, retry, confirm, cancel and reload preserve expected stock/order state.
- An incognito browser cannot access another browser's order ID.
- An event created then left with its browser closed is sent by the worker.
- Restart service and confirm existing browser workspace persists.
- Confirm /healthz returns 200 with the worker running and that provider health checks are enabled.

Source tests: `python -m unittest discover -s tests -v`. The new public-mode and supervisor tests supplement the original 30 tests. Run `python verify_demo.py` for actual contention and crash-recovery evidence. No invented production traffic or performance metrics.
