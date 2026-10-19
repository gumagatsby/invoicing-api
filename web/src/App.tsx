import { useCallback, useState } from 'react'
import { DEMO, ApiError, register, signedIn, signedInAs, signIn, signOut } from './api'
import { Customers } from './customers'
import { Invoices, NewInvoice } from './invoices'
import { go, useRoute } from './hooks'
import { Problem } from './ui'
import { Webhooks } from './webhooks'

export default function App() {
  const [authed, setAuthed] = useState(signedIn())
  const leave = useCallback(() => { signOut(); setAuthed(false) }, [])
  return authed ? <Shell onSignOut={leave} /> : <SignIn onDone={() => { setAuthed(true); go('invoices') }} />
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function attempt(fn: () => Promise<void>) {
    setBusy(true); setError('')
    try { await fn(); onDone() } catch (e) {
      setError(e instanceof ApiError && e.status === 401 && fn === demo
        ? 'The demo account isn’t there. Start the stack with docker compose up, which creates it.'
        : (e as Error).message)
    } finally { setBusy(false) }
  }
  const demo = () => signIn(DEMO.email, DEMO.password)

  return (
    <div className="signin">
      <div className="card">
        <h1>Invoicing</h1>
        <p className="lead">Send invoices, record payments and keep the books balanced.</p>
        <button className="btn primary wide" disabled={busy} onClick={() => attempt(demo)}>Try the demo</button>
        <p className="hint centre">Signs you in to an account with sample invoices. It is rebuilt each time the stack starts.</p>
        <div className="or">{creating ? 'or create an account' : 'or sign in'}</div>
        <form onSubmit={e => { e.preventDefault(); void attempt(() => creating ? register(email, password) : signIn(email, password)) }}>
          <label>Email<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Password
            <input type="password" autoComplete={creating ? 'new-password' : 'current-password'} required
              value={password} onChange={e => setPassword(e.target.value)} aria-describedby="pw-rule" />
            <span className="hint" id="pw-rule">At least 12 characters.</span>
          </label>
          <Problem text={error} />
          <button className="btn wide" type="submit" disabled={busy}>{creating ? 'Create account' : 'Sign in'}</button>
        </form>
        <p className="swap">
          {creating ? 'Already have an account? ' : 'New here? '}
          <button className="link" onClick={() => { setCreating(!creating); setError('') }}>{creating ? 'Sign in' : 'Create an account'}</button>
        </p>
      </div>
    </div>
  )
}

function Shell({ onSignOut }: { onSignOut: () => void }) {
  const route = useRoute()
  const [section = 'invoices', id] = route
  const isDemo = signedInAs() === DEMO.email
  const nav = (key: string, label: string) =>
    <a href={`#/${key}`} aria-current={section === key ? 'page' : undefined}>{label}</a>
  return (
    <div className="app">
      <nav className="side" aria-label="Sections">
        <div className="brand">Invoicing{isDemo && <span className="demo">Demo</span>}</div>
        {nav('invoices', 'Invoices')}
        {nav('customers', 'Customers')}
        {nav('webhooks', 'Webhooks')}
        <div className="who"><span>{signedInAs()}</span><button className="link" onClick={onSignOut}>Sign out</button></div>
      </nav>
      <main className="main">
        {section === 'customers' ? <Customers onAuthLost={onSignOut} />
          : section === 'webhooks' ? <Webhooks onAuthLost={onSignOut} />
          : id === 'new' ? <NewInvoice onAuthLost={onSignOut} />
          : <Invoices selected={id ?? null} onAuthLost={onSignOut} />}
      </main>
    </div>
  )
}
