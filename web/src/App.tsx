import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, money, signedIn, signIn, signOut, type Balances, type Currency, type Customer, type Invoice, type LedgerRow, type Payment } from './api'

export default function App() {
  const [authed, setAuthed] = useState(signedIn())
  return authed ? <Dashboard onSignOut={() => { signOut(); setAuthed(false) }} /> : <SignIn onDone={() => setAuthed(true)} />
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [register, setRegister] = useState(false)
  const [error, setError] = useState('')
  return (
    <main className="narrow">
      <h1>Invoicing</h1>
      <form onSubmit={async e => {
        e.preventDefault(); setError('')
        try { await signIn(email, password, register); onDone() } catch (err) { setError((err as Error).message) }
      }}>
        <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" required minLength={12} value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit">{register ? 'Create account' : 'Sign in'}</button>
        <button type="button" className="link" onClick={() => setRegister(!register)}>
          {register ? 'I already have an account' : 'Create an account'}
        </button>
      </form>
    </main>
  )
}

function Dashboard({ onSignOut }: { onSignOut: () => void }) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [balances, setBalances] = useState<Balances>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [inv, cus, bal] = await Promise.all([api.invoices(), api.customers(), api.balances()])
      setInvoices(inv.items); setCustomers(cus); setBalances(bal)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onSignOut(); else setError((e as Error).message)
    }
  }, [onSignOut])
  useEffect(() => { void load() }, [load])

  return (
    <main>
      <header><h1>Invoicing</h1><button className="link" onClick={onSignOut}>Sign out</button></header>
      {error && <p className="error" role="alert">{error}</p>}
      <section>
        <h2>Ledger</h2>
        {Object.keys(balances).length === 0 ? <p className="muted">No entries yet.</p> : (
          <table>
            <thead><tr><th>Currency</th><th>Cash</th><th>Receivables</th><th>Revenue</th><th>Balanced</th></tr></thead>
            <tbody>{Object.entries(balances).map(([cur, accts]) => {
              const bal = (a: string) => { const v = accts[a]; return typeof v === 'object' ? money(v.balance_minor, cur as Currency) : '–' }
              return <tr key={cur}><td>{cur}</td><td>{bal('cash')}</td><td>{bal('receivables')}</td><td>{bal('revenue')}</td><td>{accts._balanced ? 'Yes' : 'No'}</td></tr>
            })}</tbody>
          </table>
        )}
      </section>
      <section>
        <h2>Invoices</h2>
        <table>
          <thead><tr><th>Customer</th><th>Created</th><th>Total</th><th>Outstanding</th><th>Status</th><th>Due</th></tr></thead>
          <tbody>{invoices.map(i => (
            <tr key={i.id} className={i.id === selected ? 'selected' : ''} onClick={() => setSelected(i.id)}>
              <td>{customers.find(c => c.id === i.customer_id)?.name ?? ''}</td>
              <td>{new Date(i.created_at).toLocaleDateString('en-GB')}</td><td>{money(i.total_minor, i.currency)}</td>
              <td>{money(i.outstanding_minor, i.currency)}</td><td>{i.status}</td><td>{i.due_date}</td>
            </tr>))}</tbody>
        </table>
        {invoices.length === 0 && <p className="muted">No invoices yet.</p>}
      </section>
      {selected && <InvoiceDetail id={selected} onChange={load} />}
      <NewInvoice customers={customers} onCreated={load} />
    </main>
  )
}

function InvoiceDetail({ id, onChange }: { id: string; onChange: () => void }) {
  const [inv, setInv] = useState<Invoice | null>(null)
  const [payments, setPayments] = useState<Payment[]>([])
  const [ledger, setLedger] = useState<LedgerRow[]>([])
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    const [i, p, l] = await Promise.all([api.invoice(id), api.payments(id), api.ledger(id)])
    setInv(i); setPayments(p); setLedger(l)
  }, [id])
  useEffect(() => { void refresh() }, [refresh])
  if (!inv) return null
  return (
    <section>
      <h2>Invoice {inv.id.slice(0, 8)}</h2>
      <p>{money(inv.paid_minor, inv.currency)} paid of {money(inv.total_minor, inv.currency)}.</p>
      {inv.status === 'open' && (
        <form className="inline" onSubmit={async e => {
          e.preventDefault(); setError('')
          try {
            await api.pay(id, Math.round(parseFloat(amount) * 100), inv.currency, crypto.randomUUID())
            setAmount(''); await refresh(); onChange()
          } catch (err) { setError((err as Error).message) }
        }}>
          <label>Amount ({inv.currency})<input inputMode="decimal" required pattern="\d+(\.\d{1,2})?" value={amount} onChange={e => setAmount(e.target.value)} /></label>
          <button type="submit">Record payment</button>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <h3>Payments</h3>
      {payments.length === 0 ? <p className="muted">None yet.</p> : (
        <ul>{payments.map(p => <li key={p.id}>{money(p.amount_minor, p.currency)} on {new Date(p.created_at).toLocaleString('en-GB')}</li>)}</ul>
      )}
      <h3>Ledger entries</h3>
      <table>
        <thead><tr><th>Account</th><th>Debit</th><th>Credit</th><th>Memo</th></tr></thead>
        <tbody>{ledger.map((r, n) => (
          <tr key={n}><td>{r.account}</td><td>{r.debit_minor ? money(r.debit_minor, r.currency) : ''}</td>
            <td>{r.credit_minor ? money(r.credit_minor, r.currency) : ''}</td><td>{r.memo}</td></tr>))}</tbody>
      </table>
    </section>
  )
}

function NewInvoice({ customers, onCreated }: { customers: Customer[]; onCreated: () => void }) {
  const [customer, setCustomer] = useState('')
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [currency, setCurrency] = useState<Currency>('GBP')
  const [description, setDescription] = useState('')
  const [price, setPrice] = useState('')
  const [error, setError] = useState('')
  return (
    <section>
      <h2>New invoice</h2>
      <form onSubmit={async e => {
        e.preventDefault(); setError('')
        try {
          const customerId = customer || (await api.addCustomer(newName, newEmail)).id
          const due = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10)
          await api.createInvoice({ customer_id: customerId, currency, due_date: due,
            lines: [{ description, quantity: 1, unit_price_minor: Math.round(parseFloat(price) * 100) }] })
          setDescription(''); setPrice(''); onCreated()
        } catch (err) { setError((err as Error).message) }
      }}>
        <label>Customer
          <select value={customer} onChange={e => setCustomer(e.target.value)}>
            <option value="">New customer</option>
            {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        {!customer && <>
          <label>Customer name<input required value={newName} onChange={e => setNewName(e.target.value)} /></label>
          <label>Customer email<input type="email" required value={newEmail} onChange={e => setNewEmail(e.target.value)} /></label>
        </>}
        <label>Currency
          <select value={currency} onChange={e => setCurrency(e.target.value as Currency)}>
            <option>GBP</option><option>USD</option><option>EUR</option>
          </select>
        </label>
        <label>Work<input required value={description} onChange={e => setDescription(e.target.value)} /></label>
        <label>Price<input inputMode="decimal" required pattern="\d+(\.\d{1,2})?" value={price} onChange={e => setPrice(e.target.value)} /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit">Create invoice</button>
      </form>
    </section>
  )
}
