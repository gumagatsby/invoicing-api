# Design decisions and trade-offs

## 1. Money is an integer of minor units

Amounts are stored as `BIGINT` pence, cents or euro cents, never as floats. Floating point cannot represent 0.10 exactly, and rounding errors in money compound. Every invoice has one currency, and a payment in a different currency is refused rather than converted.

## 2. Idempotency keys on payments

A payment request must carry an `Idempotency-Key` header. If the network drops the response and the client retries with the same key, the API returns the original payment (`200`, `Idempotent-Replayed: true`) instead of charging again. Reusing a key with a different amount is a client bug, so it gets `409 Conflict`. The key is unique per merchant in the database, so even a bug in the application cannot record two payments for one key.

## 3. Row locks stop concurrent overpayment

Taking a payment locks the invoice row (`SELECT ... FOR UPDATE`) before reading the outstanding balance. Two simultaneous payments therefore run one after the other: the second sees the first and is refused if it would overpay. A `CHECK` constraint (`paid_minor <= total_minor`) is the last line of defence. Both behaviours are tested with real concurrent requests against PostgreSQL: 20 retries with one key create one payment, and 10 different full payments on one invoice produce exactly one success.

**Alternative considered:** optimistic locking with a version column and retries. It scales better when contention is rare, but pessimistic locking is simpler to reason about and contention on one invoice is rare enough that the lock is held for milliseconds.

## 4. A double-entry ledger, append-only

Issuing an invoice debits receivables and credits revenue. A payment debits cash and credits receivables. Voiding writes reversing entries rather than deleting anything. Debits always equal credits, which `/ledger/balances` checks and a test asserts. This is how accountants and payment companies keep books: any balance can be rebuilt from the entries, and nothing is edited after the fact.

## 5. Webhooks through an outbox, signed, retried

When a payment succeeds, the webhook delivery rows are written **in the same transaction** as the payment (the transactional outbox pattern). A worker sends due deliveries every five seconds. So a crash after the payment commits cannot lose the event, and a crash before it commits sends nothing false.

- Signed: each request carries `Invoicing-Signature: t=<timestamp>,v1=<HMAC-SHA256 of timestamp.body>`. Receivers verify it with the secret they were given once, and reject anything older than five minutes, which stops replays.
- Retried: failures back off 1, 2, 4, 8 and 16 minutes, then the delivery is marked failed after 6 attempts and stays visible in `/webhooks/{id}/deliveries`.
- At-least-once: a receiver may see an event twice, so each event has a unique `id` for the receiver to de-duplicate on.

## 6. Short access tokens, rotating refresh tokens

Access tokens (JWT, HS256) last 15 minutes and are never stored. Refresh tokens last 7 days, work **once**, and each use issues a new one in the same "family". If a used refresh token is presented again, someone has a copy, so the whole family is revoked and the user must sign in again. Passwords are hashed with Argon2id. A failed login for an unknown email still runs a hash check, so response time does not reveal which emails exist.

## 7. Tenancy by ownership, 404 not 403

Every query filters by the caller's ID. Asking for another merchant's invoice returns 404, the same as one that does not exist, so IDs cannot be probed.

## 8. Rate limiting in Redis

A fixed one-minute window per user, counted in Redis so the limit holds across any number of API replicas. Over the limit returns `429` with `Retry-After`. A sliding window or token bucket smooths bursts at window edges; fixed window was chosen because it is one `INCR` per request and easy to explain.

## 9. Observability built in

- Metrics: Prometheus histograms of latency by route template (not raw path, which would explode cardinality), payment outcomes, and webhook attempts from the worker. Grafana is provisioned with a dashboard.
- Traces: OpenTelemetry instruments FastAPI and SQLAlchemy and exports to Jaeger, so a slow request can be followed down to the SQL statement. Tracing is off unless an endpoint is configured, so tests need nothing extra.

## 10. Tests against real PostgreSQL and Redis

Locking, unique constraints and `CHECK` constraints are database behaviour; mocking the database would test nothing that matters here. CI starts PostgreSQL and Redis as service containers, runs the suite, then builds a fresh database from the Alembic migrations and runs `alembic check` to prove the migrations match the models.

## 11. What production would add

- Payment provider integration (Stripe or similar) behind the same idempotent interface; here a "payment" records money received.
- Asymmetric JWT signing (RS256 or EdDSA) with key rotation, so other services can verify tokens without the secret.
- A sliding-window rate limiter and per-endpoint limits.
- Partitioning or archiving of the ledger table as it grows.
- A managed queue (SQS) or Kafka for webhook fan-out at higher volume.
