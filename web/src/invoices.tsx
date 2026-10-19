import { useEffect, useState } from 'react'
import { api, ApiError, day, money, moment, shown, toMinor, today, type Account, type Currency, type Customer, type Invoice, type Line } from './api'
import { go, useLoad } from './hooks'
import { Badge, Problem } from './ui'

type Filter = 'all' | 'open' | 'overdue' | 'paid' | 'void'
const FILTERS: [Filter, string][] = [['all', 'All'], ['open', 'Open'], ['overdue', 'Overdue'], ['paid', 'Paid'], ['void', 'Void']]

// Several currencies never add up to one figure: show the first and list the rest beneath it.
function perCurrency(sums: Record<string, number>) {
  const parts = Object.entries(sums).filter(([, v]) => v !== 0).map(([c, v]) => money(v, c))
  return { main: parts[0] ?? money(0, 'GBP'), rest: parts.slice(1) }
}

export function Invoices({ selected, onAuthLost }: { selected: string | null; onAuthLost: () => void }) {
  const [filter, setFilter] = useState<Filter>('all')
  const summary = useLoad(async () => {
    const [balances, open, customers] = await Promise.all([api.balances(), api.openInvoices(), api.customers()])
    return { balances, open, customers }
  }, [], onAuthLost)
  const [rows, setRows] = useState<Invoice[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [listError, setListError] = useState('')
  const [version, setVersion] = useState(0)

  // Overdue is not a stored status: it is an open invoice past its due date, so it comes from the open list.
  useEffect(() => {
    if (filter === 'overdue') return
    let live = true
    api.invoices(filter === 'all' ? undefined : filter).then(p => { if (live) { setRows(p.items); setCursor(p.next_cursor); setListError('') } })
      .catch(e => { if (e instanceof ApiError && e.status === 401) onAuthLost(); else if (live) setListError(e.message) })
    return () => { live = false }
  }, [filter, version, onAuthLost])

  const more = async () => {
    try { const p = await api.invoices(filter === 'all' ? undefined : filter as 'open' | 'paid' | 'void', cursor); setRows(r => [...r, ...p.items]); setCursor(p.next_cursor) }
    catch (e) { setListError((e as Error).message) }
  }
  const changed = () => { summary.reload(); setVersion(v => v + 1) }

  const d = summary.data
  const names = new Map((d?.customers ?? []).map((c: Customer) => [c.id, c.name]))
  const sum = (account: string) => {
    const out: Record<string, number> = {}
    for (const [cur, accts] of Object.entries(d?.balances ?? {})) {
      const a = accts[account]
      if (typeof a === 'object') out[cur] = (a as Account).balance_minor
    }
    return perCurrency(out)
  }
  const overdue = (d?.open ?? []).filter(i => shown(i) === 'overdue')
  const overdueSums: Record<string, number> = {}
  overdue.forEach(i => { overdueSums[i.currency] = (overdueSums[i.currency] ?? 0) + i.outstanding_minor })
  const out = sum('receivables'), cash = sum('cash'), late = perCurrency(overdueSums)
  const balanced = d && Object.values(d.balances).every(a => a._balanced === true)
  const visible = filter === 'overdue' ? overdue : rows

  return (
    <>
      <div className="top"><h1>Invoices</h1><a className="btn primary" href="#/invoices/new">New invoice</a></div>
      <Problem text={summary.error} />
      {d && (
        <div className="stats">
          <div className="stat"><div className="k">Outstanding</div><div className="v num">{out.main}</div>
            <div className="s">{out.rest.length ? 'and ' + out.rest.join(', ') : `${d.open.length} open ${d.open.length === 1 ? 'invoice' : 'invoices'}`}</div></div>
          <div className="stat"><div className="k">Overdue</div><div className={'v num' + (overdue.length ? ' late' : '')}>{late.main}</div>
            <div className="s">{late.rest.length ? 'and ' + late.rest.join(', ') : `${overdue.length} past due`}</div></div>
          <div className="stat"><div className="k">Collected to date</div><div className="v num">{cash.main}</div>
            <div className="s num">{cash.rest.length ? 'and ' + cash.rest.join(', ') : 'All payments received'}</div></div>
          <div className="stat"><div className="k">Books</div>
            <div className="v small">{balanced ? <span className="ok">Balanced</span> : <span className="bad">Out of balance</span>}</div>
            <div className="s">Every entry has a matching side</div></div>
        </div>
      )}
      <div className={selected ? 'split' : ''}>
        <div className="panel">
          <div className="bar">
            <div className="seg" role="group" aria-label="Show">
              {FILTERS.map(([f, label]) => <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>{label}</button>)}
            </div>
            <span className="sub hide-sm">Newest first</span>
          </div>
          <Problem text={listError} />
          {visible.length === 0 ? <p className="empty">{filter === 'all' ? 'No invoices yet. Create one to get started.' : 'Nothing here.'}</p> : (
            <table>
              <thead><tr><th>Customer</th>{!selected && <><th className="hide-sm">Issued</th><th className="hide-sm">Due</th></>}
                <th>Status</th>{!selected && <th className="r hide-sm">Total</th>}<th className="r">Still due</th></tr></thead>
              <tbody className="num">{visible.map(i => (
                <tr key={i.id} aria-selected={i.id === selected} onClick={() => go(`invoices/${i.id}`)}>
                  <td><a className="cust" href={`#/invoices/${i.id}`} onClick={e => e.stopPropagation()}>{names.get(i.customer_id) ?? 'Customer'}</a>
                    <div className="sub">{i.lines[0]?.description}{i.lines.length > 1 ? ` and ${i.lines.length - 1} more` : ''}</div></td>
                  {!selected && <><td className="hide-sm">{day(i.created_at)}</td><td className="hide-sm">{day(i.due_date)}</td></>}
                  <td><Badge status={shown(i)} /></td>
                  {!selected && <td className="r hide-sm">{money(i.total_minor, i.currency)}</td>}
                  <td className="r">{i.status === 'void' ? '–' : money(i.outstanding_minor, i.currency)}</td>
                </tr>))}</tbody>
            </table>
          )}
          {cursor && filter !== 'overdue' && <div className="pager"><span>Showing {rows.length}</span><button className="btn" onClick={more}>Load more</button></div>}
        </div>
        {selected && <InvoiceDetail key={selected} id={selected} customer={names.get(visible.find(r => r.id === selected)?.customer_id ?? '')}
          onChange={changed} onAuthLost={onAuthLost} />}
      </div>
    </>
  )
}

export function InvoiceDetail({ id, customer, onChange, onAuthLost }:
  { id: string; customer?: string; onChange: () => void; onAuthLost: () => void }) {
  const { data, error, reload } = useLoad(async () => {
    const [inv, payments, ledger, customers] = await Promise.all([api.invoice(id), api.payments(id), api.ledger(id), customer ? null : api.customers()])
    return { inv, payments, ledger, name: customer ?? customers?.find(c => c.id === inv.customer_id)?.name ?? 'Customer' }
  }, [id, customer], onAuthLost)
  // Until edited, the amount is whatever is still due.
  const [edited, setEdited] = useState<string | null>(null)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState('')
  const [confirmVoid, setConfirmVoid] = useState(false)

  if (error) return <aside className="drawer"><Problem text={error} /></aside>
  if (!data) return <aside className="drawer loading" aria-busy="true" />
  const { inv, payments, ledger, name } = data
  const status = shown(inv)
  const amount = edited ?? (inv.outstanding_minor / 100).toFixed(2)

  const pay = async () => {
    setBusy(true); setProblem('')
    try { await api.pay(inv.id, toMinor(amount), inv.currency, key); setKey(crypto.randomUUID()); setEdited(null); reload(); onChange() }
    catch (e) { setProblem((e as Error).message) } finally { setBusy(false) }
  }
  const voidIt = async () => {
    setBusy(true); setProblem('')
    try { await api.voidInvoice(inv.id); setConfirmVoid(false); reload(); onChange() }
    catch (e) { setProblem((e as Error).message) } finally { setBusy(false) }
  }
  const voidedAt = ledger.find(l => l.memo === 'Invoice voided')?.created_at
  const history = [
    { at: inv.created_at, what: 'Invoice issued', amount: money(inv.total_minor, inv.currency) },
    ...payments.map(p => ({ at: p.created_at, what: 'Payment received', amount: money(p.amount_minor, p.currency) })),
    ...(voidedAt ? [{ at: voidedAt, what: 'Invoice voided', amount: '' }] : []),
  ].sort((a, b) => b.at.localeCompare(a.at))
  const share = inv.total_minor ? Math.round(inv.paid_minor / inv.total_minor * 1000) / 10 : 0

  return (
    <aside className="drawer" aria-label={`Invoice for ${name}`}>
      <header>
        <div className="drawer-title"><h2>{name}</h2><Badge status={status} />
          <a className="close" href="#/invoices" aria-label="Close">×</a></div>
        <div className="meta num">Issued {day(inv.created_at)} · Due {day(inv.due_date)} · <span className="mono">INV-{inv.id.slice(0, 8).toUpperCase()}</span></div>
      </header>
      <section>
        <table className="lines num"><tbody>
          {inv.lines.map((l, n) => <tr key={n}><td>{l.description}{l.quantity > 1 && <span className="sub">, {l.quantity} × {money(l.unit_price_minor, inv.currency)}</span>}</td>
            <td className="r">{money(l.quantity * l.unit_price_minor, inv.currency)}</td></tr>)}
          <tr className="tot"><td>Total</td><td className="r">{money(inv.total_minor, inv.currency)}</td></tr>
        </tbody></table>
      </section>
      {inv.status !== 'void' && (
        <section>
          <h3>Payment</h3>
          <div className="num"><b>{money(inv.paid_minor, inv.currency)}</b> paid of {money(inv.total_minor, inv.currency)}
            {inv.outstanding_minor > 0 && <> · <b>{money(inv.outstanding_minor, inv.currency)}</b> still due</>}</div>
          <div className="progress" role="progressbar" aria-valuenow={share} aria-valuemin={0} aria-valuemax={100} aria-label="Paid">
            <span style={{ width: `${share}%` }} /></div>
          {inv.status === 'open' && (
            <form className="pay" onSubmit={e => { e.preventDefault(); void pay() }}>
              <label>Amount ({inv.currency})
                <input className="num" inputMode="decimal" required pattern="\d+(\.\d{1,2})?" value={amount}
                  onChange={e => { setEdited(e.target.value); setKey(crypto.randomUUID()) }} /></label>
              <button className="btn primary" type="submit" disabled={busy}>Record payment</button>
            </form>
          )}
          {inv.status === 'open' && <p className="hint">Safe to press twice: the same payment is only ever recorded once.</p>}
        </section>
      )}
      <Problem text={problem} />
      <section>
        <h3>History</h3>
        <ul className="timeline num">{history.map((h, n) => <li key={n}><span>{h.what}</span><span className="sub">{h.amount && h.amount + ' · '}{moment(h.at)}</span></li>)}</ul>
      </section>
      <section>
        <details><summary>Accounting entries ({ledger.length})</summary>
          <table className="num entries"><thead><tr><th>Account</th><th className="r">Debit</th><th className="r">Credit</th></tr></thead>
            <tbody>{ledger.map((r, n) => <tr key={n}><td className="cap">{r.account}<div className="sub">{r.memo}</div></td>
              <td className="r">{r.debit_minor ? money(r.debit_minor, r.currency) : ''}</td><td className="r">{r.credit_minor ? money(r.credit_minor, r.currency) : ''}</td></tr>)}</tbody>
          </table>
        </details>
      </section>
      {inv.status === 'open' && inv.paid_minor === 0 && (
        <section className="actions">
          {confirmVoid ? <>
            <span className="sub">Void this invoice? It stays on record, reversed in the books.</span>
            <button className="btn danger" disabled={busy} onClick={voidIt}>Void</button>
            <button className="btn quiet" onClick={() => setConfirmVoid(false)}>Keep</button>
          </> : <button className="btn danger" onClick={() => setConfirmVoid(true)}>Void invoice</button>}
        </section>
      )}
    </aside>
  )
}

interface Draft { description: string; quantity: string; price: string }
const blank = (): Draft => ({ description: '', quantity: '1', price: '' })

export function NewInvoice({ onAuthLost }: { onAuthLost: () => void }) {
  const { data: customers } = useLoad(api.customers, [], onAuthLost)
  const [customer, setCustomer] = useState('')
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [currency, setCurrency] = useState<Currency>('GBP')
  const [in30] = useState(() => new Date(Date.now() + 30 * 864e5).toLocaleDateString('en-CA'))
  const [due, setDue] = useState(in30)
  const [lines, setLines] = useState<Draft[]>([blank()])
  const [problem, setProblem] = useState('')
  const [busy, setBusy] = useState(false)

  const amount = (l: Draft) => (parseInt(l.quantity) || 0) * (toMinor(l.price) || 0)
  const total = lines.reduce((t, l) => t + amount(l), 0)
  const edit = (n: number, field: keyof Draft, value: string) => setLines(ls => ls.map((l, i) => i === n ? { ...l, [field]: value } : l))
  const adding = customer === '' && (customers?.length ?? 0) === 0 || customer === 'new'

  const submit = async () => {
    setBusy(true); setProblem('')
    try {
      const customerId = adding ? (await api.addCustomer(newName, newEmail)).id : customer
      if (!customerId) throw new Error('Choose a customer.')
      const inv = await api.createInvoice({ customer_id: customerId, currency, due_date: due,
        lines: lines.map((l): Line => ({ description: l.description, quantity: parseInt(l.quantity), unit_price_minor: toMinor(l.price) })) })
      go(`invoices/${inv.id}`)
    } catch (e) { setProblem((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <>
      <div className="top"><h1>New invoice</h1></div>
      <form className="panel form" onSubmit={e => { e.preventDefault(); void submit() }}>
        <div className="row">
          <label>Customer
            <select value={adding ? 'new' : customer} onChange={e => setCustomer(e.target.value)} required>
              {(customers?.length ?? 0) > 0 && <option value="">Choose a customer</option>}
              {customers?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              <option value="new">New customer</option>
            </select></label>
          <label>Currency
            <select value={currency} onChange={e => setCurrency(e.target.value as Currency)}>
              <option>GBP</option><option>USD</option><option>EUR</option></select></label>
          <label>Due date<input type="date" required value={due} min={today()} onChange={e => setDue(e.target.value)} />
            {due === in30 && <span className="hint">30 days from today</span>}</label>
        </div>
        {adding && <div className="row two">
          <label>Customer name<input required value={newName} onChange={e => setNewName(e.target.value)} /></label>
          <label>Customer email<input type="email" required value={newEmail} onChange={e => setNewEmail(e.target.value)} /></label>
        </div>}
        <table className="items num">
          <thead><tr><th className="grow">Item</th><th>Qty</th><th>Unit price</th><th className="r">Amount</th><th><span className="vh">Remove</span></th></tr></thead>
          <tbody>{lines.map((l, n) => (
            <tr key={n}>
              <td><input aria-label={`Item ${n + 1}`} required value={l.description} onChange={e => edit(n, 'description', e.target.value)} /></td>
              <td><input aria-label={`Quantity ${n + 1}`} inputMode="numeric" required pattern="[1-9]\d*" value={l.quantity} onChange={e => edit(n, 'quantity', e.target.value)} /></td>
              <td><input aria-label={`Unit price ${n + 1}`} inputMode="decimal" required pattern="\d+(\.\d{1,2})?" value={l.price} onChange={e => edit(n, 'price', e.target.value)} /></td>
              <td className="r">{money(amount(l), currency)}</td>
              <td>{lines.length > 1 && <button type="button" className="btn quiet" aria-label={`Remove item ${n + 1}`} onClick={() => setLines(ls => ls.filter((_, i) => i !== n))}>×</button>}</td>
            </tr>))}</tbody>
        </table>
        <div><button type="button" className="btn quiet" onClick={() => setLines(ls => [...ls, blank()])}>+ Add a line</button></div>
        <div className="totalrow"><span className="sub">Total</span><span className="v num">{money(total, currency)}</span></div>
        <Problem text={problem} />
        <div className="actions end"><a className="btn quiet" href="#/invoices">Cancel</a><button className="btn primary" type="submit" disabled={busy}>Create invoice</button></div>
      </form>
    </>
  )
}
