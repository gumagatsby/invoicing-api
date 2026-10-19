import { useState } from 'react'
import { api } from './api'
import { useLoad } from './hooks'
import { Problem } from './ui'

export function Customers({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, error, reload } = useLoad(api.customers, [], onAuthLost)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [problem, setProblem] = useState('')
  const add = async () => {
    setProblem('')
    try { await api.addCustomer(name, email); setName(''); setEmail(''); reload() } catch (e) { setProblem((e as Error).message) }
  }
  return (
    <>
      <div className="top"><h1>Customers</h1></div>
      <Problem text={error} />
      <form className="panel inline-add" onSubmit={e => { e.preventDefault(); void add() }}>
        <label>Name<input required value={name} onChange={e => setName(e.target.value)} /></label>
        <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <button className="btn primary" type="submit">Add customer</button>
      </form>
      <Problem text={problem} />
      <div className="panel">
        {data && data.length === 0 ? <p className="empty">No customers yet.</p> : (
          <table><thead><tr><th>Name</th><th>Email</th></tr></thead>
            <tbody>{data?.map(c => <tr key={c.id} className="still"><td className="cust">{c.name}</td><td>{c.email}</td></tr>)}</tbody></table>
        )}
      </div>
    </>
  )
}
