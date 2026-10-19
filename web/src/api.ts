// Typed client for the Invoicing API. In development Vite proxies /api; in Docker, nginx does.
const BASE = '/api'

export type Currency = 'GBP' | 'USD' | 'EUR'
export type Status = 'open' | 'paid' | 'void'
export interface Line { description: string; quantity: number; unit_price_minor: number }
export interface Invoice {
  id: string
  customer_id: string
  currency: Currency
  status: Status
  due_date: string
  total_minor: number
  paid_minor: number
  outstanding_minor: number
  created_at: string
  lines: Line[]
}
export interface Page { items: Invoice[]; next_cursor: string | null }
export interface Customer { id: string; name: string; email: string }
export interface Payment { id: string; amount_minor: number; currency: Currency; created_at: string }
export interface LedgerRow { account: string; debit_minor: number; credit_minor: number; currency: Currency; memo: string; created_at: string }
export interface Account { debit_minor: number; credit_minor: number; balance_minor: number }
export type Balances = Record<string, Record<string, Account | boolean>>
export interface Endpoint { id: string; url: string; active: boolean; secret?: string | null }
export interface Delivery { id: string; event: string; status: 'pending' | 'delivered' | 'failed'; attempts: number; last_status_code: number | null; created_at: string }

// The demo account, created by the stack's `demo` service. Not a secret.
export const DEMO = { email: 'demo@example.com', password: 'demo-account-not-secret' }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

let access: string | null = sessionStorage.getItem('access')
let refreshToken: string | null = sessionStorage.getItem('refresh')
let email: string | null = sessionStorage.getItem('email')
export const signedIn = () => access !== null
export const signedInAs = () => email ?? ''
export function signOut() {
  access = refreshToken = email = null
  sessionStorage.clear()
}
function keep(tokens: { access_token: string; refresh_token: string }) {
  access = tokens.access_token; refreshToken = tokens.refresh_token
  sessionStorage.setItem('access', access); sessionStorage.setItem('refresh', refreshToken)
}

async function detail(res: Response) {
  const body = await res.json().catch(() => ({}))
  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail) && body.detail[0]?.msg) return String(body.detail[0].msg)
  return res.statusText || 'Something went wrong'
}

// Access tokens last 15 minutes. On a 401, trade the refresh token for new ones once, then retry.
// Refresh tokens are single use, so requests that fail together share one renewal.
let renewing: Promise<boolean> | null = null
function renew() {
  renewing ??= (async () => {
    if (!refreshToken) return false
    const res = await fetch(BASE + '/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }) })
    if (!res.ok) return false
    keep(await res.json())
    return true
  })().finally(() => { renewing = null })
  return renewing
}

async function call<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const sent = access
  const res = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(sent ? { Authorization: `Bearer ${sent}` } : {}), ...init.headers },
  })
  // A request sent with a token that has since been replaced just tries again with the new one.
  if (res.status === 401 && !retried && (access !== sent || await renew())) return call(path, init, true)
  if (res.status === 401) signOut()
  if (!res.ok) throw new ApiError(res.status, await detail(res))
  return res.json() as Promise<T>
}

export async function signIn(address: string, password: string) {
  const res = await fetch(BASE + '/auth/token', { method: 'POST', body: new URLSearchParams({ username: address, password }) })
  // The API gives one answer for a wrong password and an unknown email, so nobody can test which emails have accounts.
  if (res.status === 401) throw new ApiError(401, "That email and password don't match.")
  if (!res.ok) throw new ApiError(res.status, await detail(res))
  keep(await res.json())
  email = address.toLowerCase(); sessionStorage.setItem('email', email)
}

export async function register(address: string, password: string) {
  const res = await fetch(BASE + '/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: address, password }) })
  if (res.status === 409) throw new ApiError(409, 'That email already has an account. Sign in instead.')
  if (!res.ok) throw new ApiError(res.status, await detail(res))
  await signIn(address, password)
}

export const api = {
  customers: () => call<Customer[]>('/customers'),
  addCustomer: (name: string, address: string) =>
    call<Customer>('/customers', { method: 'POST', body: JSON.stringify({ name, email: address }) }),
  invoices: (status?: Status, cursor?: string | null, limit = 25) => {
    const q = new URLSearchParams({ limit: String(limit) })
    if (status) q.set('status', status)
    if (cursor) q.set('cursor', cursor)
    return call<Page>(`/invoices?${q}`)
  },
  // Every open invoice, page by page: the overdue figures need all of them.
  openInvoices: async () => {
    const all: Invoice[] = []
    let cursor: string | null = null
    do {
      const page: Page = await api.invoices('open', cursor, 100)
      all.push(...page.items); cursor = page.next_cursor
    } while (cursor)
    return all
  },
  invoice: (id: string) => call<Invoice>(`/invoices/${id}`),
  createInvoice: (body: { customer_id: string; currency: Currency; due_date: string; lines: Line[] }) =>
    call<Invoice>('/invoices', { method: 'POST', body: JSON.stringify(body) }),
  voidInvoice: (id: string) => call<Invoice>(`/invoices/${id}/void`, { method: 'POST' }),
  payments: (id: string) => call<Payment[]>(`/invoices/${id}/payments`),
  ledger: (id: string) => call<LedgerRow[]>(`/ledger?invoice_id=${id}`),
  balances: () => call<Balances>('/ledger/balances'),
  // The key belongs to one intended payment, not one click: pressing twice, or a network retry, sends the
  // same key, and the API records the payment once.
  pay: async (id: string, amount_minor: number, currency: Currency, key: string) => {
    for (let attempt = 0; ; attempt++) {
      try {
        return await call<Payment>(`/invoices/${id}/payments`, {
          method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ amount_minor, currency }),
        })
      } catch (e) {
        if (e instanceof ApiError || attempt >= 2) throw e // only retry network failures
      }
    }
  },
  webhooks: () => call<Endpoint[]>('/webhooks'),
  addWebhook: (url: string) => call<Endpoint>('/webhooks', { method: 'POST', body: JSON.stringify({ url }) }),
  deliveries: (id: string) => call<Delivery[]>(`/webhooks/${id}/deliveries`),
}

export const money = (minor: number, currency: string) =>
  new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(minor / 100)
export const toMinor = (text: string) => Math.round(parseFloat(text) * 100)
export const day = (iso: string) =>
  new Date(iso.length === 10 ? iso + 'T00:00:00' : iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
export const moment = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
export const today = () => new Date().toLocaleDateString('en-CA')
export type Shown = Status | 'overdue'
export const shown = (inv: Invoice): Shown => inv.status === 'open' && inv.due_date < today() ? 'overdue' : inv.status
