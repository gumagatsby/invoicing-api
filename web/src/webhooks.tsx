import { useEffect, useState } from 'react'
import { api, moment, type Delivery, type Endpoint } from './api'
import { useLoad } from './hooks'
import { Problem } from './ui'

const RESULT: Record<Delivery['status'], [string, string]> = {
  delivered: ['Delivered', 'd-ok'], pending: ['Retrying', 'd-retry'], failed: ['Failed', 'd-fail'],
}

export function Webhooks({ onAuthLost }: { onAuthLost: () => void }) {
  const { data: endpoints, error, reload } = useLoad(api.webhooks, [], onAuthLost)
  const [chosen, setChosen] = useState<string | null>(null)
  const [url, setUrl] = useState('')
  const [created, setCreated] = useState<Endpoint | null>(null)
  const [copied, setCopied] = useState(false)
  const [problem, setProblem] = useState('')
  const current = chosen ?? endpoints?.[0]?.id ?? null

  const add = async () => {
    setProblem('')
    try { const ep = await api.addWebhook(url); setCreated(ep); setCopied(false); setUrl(''); setChosen(ep.id); reload() }
    catch (e) { setProblem((e as Error).message) }
  }

  return (
    <>
      <div className="top"><h1>Webhooks</h1></div>
      <p className="intro">Each payment and each fully paid invoice is sent to your endpoints as a signed event. The event is saved with the
        payment in the same transaction, so a crash cannot lose it, and a failed delivery is tried again with growing gaps.</p>
      <Problem text={error} />
      {created?.secret && (
        <div className="secret" role="status">
          <b>Signing secret for {created.url}</b>
          <code>{created.secret}</code>
          <div className="secret-row">
            <span className="hint">Shown once. Your server checks each delivery's Invoicing-Signature header with it (HMAC SHA-256 over the timestamp and body).</span>
            <button className="btn" onClick={() => { void navigator.clipboard.writeText(created.secret!); setCopied(true) }}>{copied ? 'Copied' : 'Copy'}</button>
          </div>
        </div>
      )}
      <form className="panel inline-add" onSubmit={e => { e.preventDefault(); void add() }}>
        <label>Endpoint URL<input type="url" required placeholder="https://" value={url} onChange={e => setUrl(e.target.value)} /></label>
        <button className="btn primary" type="submit">Add endpoint</button>
      </form>
      <Problem text={problem} />
      {endpoints && endpoints.length > 0 && (
        <div className="panel">
          <table><thead><tr><th>Endpoint</th><th>Status</th></tr></thead>
            <tbody>{endpoints.map(e => (
              <tr key={e.id} aria-selected={e.id === current} onClick={() => setChosen(e.id)}>
                <td className="mono wrap">{e.url}</td><td><span className={`dot ${e.active ? 'd-ok' : 'd-fail'}`}>{e.active ? 'Active' : 'Off'}</span></td>
              </tr>))}</tbody></table>
        </div>
      )}
      {endpoints && endpoints.length === 0 && <div className="panel"><p className="empty">No endpoints yet. Add one to start receiving events.</p></div>}
      {current && <Deliveries id={current} onAuthLost={onAuthLost} />}
    </>
  )
}

function Deliveries({ id, onAuthLost }: { id: string; onAuthLost: () => void }) {
  const { data, reload } = useLoad(() => api.deliveries(id), [id], onAuthLost)
  // The worker sends due deliveries every few seconds; keep the list current while it is open.
  useEffect(() => { const t = setInterval(reload, 5000); return () => clearInterval(t) })
  return (
    <div className="panel">
      <div className="bar"><b>Deliveries</b><span className="sub">Up to 6 attempts, each after a longer wait</span></div>
      {data && data.length === 0 ? <p className="empty">No events yet. They appear when a payment is recorded.</p> : (
        <table className="num"><thead><tr><th>Event</th><th>Result</th><th className="r">Attempts</th><th className="r hide-sm">Response</th><th className="hide-sm">Event time</th></tr></thead>
          <tbody>{data?.map(d => (
            <tr key={d.id} className="still">
              <td className="mono">{d.event}</td>
              <td><span className={`dot ${RESULT[d.status][1]}`}>{d.status === 'failed' ? `Failed after ${d.attempts} attempts`
                : d.status === 'pending' && d.attempts === 0 ? 'Queued' : RESULT[d.status][0]}</span></td>
              <td className="r">{d.attempts}</td><td className="r hide-sm mono">{d.last_status_code ?? '–'}</td><td className="hide-sm">{moment(d.created_at)}</td>
            </tr>))}</tbody></table>
      )}
    </div>
  )
}
