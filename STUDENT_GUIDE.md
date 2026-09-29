# Own the project before putting it on a resume
Run tests and demo, trace the transaction, then make and test an improvement yourself.

1. Add atomic multi-item orders: requesting two SKUs must reserve both or neither. Test insufficient stock on the second SKU.
2. Add a cleanup command: expire abandoned holds without waiting for another API request. Test repeated cleanup restores stock only once.

Do not claim distributed scale, real customers, or measured performance beyond the published workload. In an interview say the baseline was AI-assisted, explain your verified contribution, and show its commit and tests.
