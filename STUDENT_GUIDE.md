# Turn the baseline into your own work
The application was initially built with AI assistance. Repo ownership alone does not mean you independently designed every component. Before putting it on a resume, run it, trace each transaction, then make an improvement you can defend.

## Two substantive next contributions
1. **Versioned event delivery:** add an order version to events and a receiver policy for out-of-order delivery. Test a confirm event arriving before the held event, and duplicate versions arriving twice.
2. **Paginated operations views:** add stable cursor pagination instead of the latest-100 limit. Test orders with equal timestamps and inserting a new order between page reads without duplicates or omissions.

For each contribution: write down the problem, explain your design choice, add failure tests, and commit the change. Show that commit during an interview.

## Questions you must answer
- What rolls back if the second SKU is out of stock? Why is `BEGIN IMMEDIATE` useful here?
- Why can a delivered event be retried? How does the claim token prevent a stale worker from acknowledging it?
- Why is order value not revenue? Why are integer paise used?
- What would break if this were exposed publicly without authentication? What changes would PostgreSQL require?

Only claim evidence you reproduced. Two truthful descriptions after learning the code: "Ran a concurrency experiment confirming no overselling for 50 requests against 10 units" and "Verified local receiver deduplication after a delivery-before-ack crash." Describe independently implemented enhancements separately.
