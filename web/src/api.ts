// Typed client for the Invoicing API. In development Vite proxies /api; in Docker, nginx does.
const BASE = '/api'

export type Currency = 'GBP' | 'USD' | 'EUR'
export interface Invoice {
  id: string
  customer_id: string
  currency: Currency
  status: 'open' | 'paid' | 'void'
  due_date: string
  total_minor: number
  paid_minor: number
  outstanding_minor: number
  created_at: string
  lines: { description: string; quantity: number; unit_price_minor: number }[]
}
export interface Customer { id: string; name: string; email: string }
export interface Payment { id: string; amount_minor: number; currency: Currency; created_at: string }
export interface LedgerRow { account: string; debit_minor: number; credit_minor: number; currency: Currency; memo: string; created_at: string }
export type Balances = Record<string, Record<string, { debit_minor: number; credit_minor: number; balance_minor: number } | boolean>>

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

let token: string | null = sessionStorage.getItem('token')
export const signedIn = () => token !== null
export const signOut = () => { token = null; sessionStorage.removeItem('token') }

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  })
  if (res.status === 401 && token) signOut()
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : res.statusText
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export async function signIn(email: string, password: string, register: boolean) {
  if (register) await call('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) })
  const form = new URLSearchParams({ username: email, password })
  const res = await fetch(BASE + '/auth/token', { method: 'POST', body: form })
  if (!res.ok) throw new ApiError(res.status, 'Incorrect email or password')
  token = (await res.json()).access_token as string
  sessionStorage.setItem('token', token)
}

export const api = {
  customers: () => call<Customer[]>('/customers'),
  addCustomer: (name: string, email: string) => call<Customer>('/customers', { method: 'POST', body: JSON.stringify({ name, email }) }),
  invoices: () => call<{ items: Invoice[]; next_cursor: string | null }>('/invoices?limit=50'),
  invoice: (id: string) => call<Invoice>(`/invoices/${id}`),
  createInvoice: (body: { customer_id: string; currency: Currency; due_date: string; lines: Invoice['lines'] }) =>
    call<Invoice>('/invoices', { method: 'POST', body: JSON.stringify(body) }),
  payments: (id: string) => call<Payment[]>(`/invoices/${id}/payments`),
  ledger: (id: string) => call<LedgerRow[]>(`/ledger?invoice_id=${id}`),
  balances: () => call<Balances>('/ledger/balances'),
  // One idempotency key per payment attempt. A network retry reuses the key, so the
  // customer can never be charged twice for one click.
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
}

export const money = (minor: number, currency: Currency) =>
  new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(minor / 100)
