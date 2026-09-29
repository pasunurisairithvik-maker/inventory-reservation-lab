# A five-minute OrderOps walkthrough
1. Run `python launch.py` and open http://127.0.0.1:8004. Demo inventory has five products and two fictional sample orders. The active sample hold expires after one hour; expired keys do not renew automatically.
2. Create an order with one backpack and one notebook. Confirm it in Orders. Observe the reserved stock becoming sold stock and the confirmed order value increasing.
3. Create another multi-item order and cancel it. Observe stock return. Retry the same request key with identical data through /docs; observe the original order rather than a new hold. Changed payloads conflict.
4. Open Event delivery. Process an event. Simulate a delivery failure on a ready event; wait for its retry delay and process it again. Three failed attempts move an event to dead-letter. Replay restores it to pending, retaining its event ID.
5. Open Reliability lab. Run the stock contention experiment and crash experiment. These use temporary databases and leave dashboard stock unchanged.

No real customer data is needed. No external messages or transactions occur. The one-command launcher starts automatic delivery. For manual failure inspection, start only the API using the manual README commands; start `python worker.py` separately when ready.

## Interview demonstrations
- Explain why two independent read-then-write stock checks race, then show the multi-item rollback test.
- Explain the crash between receiver commit and worker acknowledgement, then show the duplicate-event and stale-token test.

If a command fails, copy its error and Python version into a local issue for diagnosis. Do not delete your database merely to hide an error. The launcher seeds idempotently and refuses to overwrite stock.
