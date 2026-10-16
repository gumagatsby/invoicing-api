from prometheus_client import Counter, Histogram

REQUESTS = Histogram("http_request_duration_seconds", "HTTP request latency", ["method", "route", "status"],
                     buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
PAYMENTS = Counter("payments_total", "Payment requests that succeeded", ["outcome"])  # created | replayed
WEBHOOKS = Counter("webhook_attempts_total", "Webhook delivery attempts", ["result"])  # delivered | retry | failed
