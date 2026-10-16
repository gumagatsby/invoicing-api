// k6 load test: each virtual user signs up once, then repeatedly creates an invoice and pays it,
// replaying every payment once with the same idempotency key, as a retrying client would.
import http from 'k6/http'
import { check } from 'k6'
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js'

const API = __ENV.API || 'http://api:8000'
export const options = {
  scenarios: { steady: { executor: 'constant-vus', vus: 20, duration: '60s' } },
  thresholds: { http_req_failed: ['rate<0.01'], 'http_req_duration{name:pay}': ['p(95)<300'] },
}

export function setup() { return {} }

export default function () {
  if (!globalThis.auth) {
    const email = `load-${uuidv4()}@example.com`
    http.post(`${API}/auth/register`, JSON.stringify({ email, password: 'load test password' }), { headers: { 'Content-Type': 'application/json' } })
    const t = http.post(`${API}/auth/token`, { username: email, password: 'load test password' })
    globalThis.auth = { Authorization: `Bearer ${t.json('access_token')}`, 'Content-Type': 'application/json' }
    globalThis.customer = http.post(`${API}/customers`, JSON.stringify({ name: 'Load Co', email: 'ap@load.example' }), { headers: globalThis.auth }).json('id')
  }
  const h = globalThis.auth
  const inv = http.post(`${API}/invoices`, JSON.stringify({ customer_id: globalThis.customer, currency: 'GBP', due_date: '2026-12-31',
    lines: [{ description: 'Load', quantity: 1, unit_price_minor: 12345 }] }), { headers: h, tags: { name: 'create_invoice' } })
  check(inv, { 'invoice 201': r => r.status === 201 })
  const key = uuidv4()
  const body = JSON.stringify({ amount_minor: 12345, currency: 'GBP' })
  const pay = http.post(`${API}/invoices/${inv.json('id')}/payments`, body, { headers: { ...h, 'Idempotency-Key': key }, tags: { name: 'pay' } })
  const replay = http.post(`${API}/invoices/${inv.json('id')}/payments`, body, { headers: { ...h, 'Idempotency-Key': key }, tags: { name: 'pay' } })
  check(pay, { 'pay 201': r => r.status === 201 })
  check(replay, { 'replay 200 same id': r => r.status === 200 && r.json('id') === pay.json('id') })
}
