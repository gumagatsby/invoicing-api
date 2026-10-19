import type { Shown } from './api'

const LABEL: Record<Shown, string> = { open: 'Open', overdue: 'Overdue', paid: 'Paid', void: 'Void' }
export const Badge = ({ status }: { status: Shown }) => <span className={`badge b-${status}`}>{LABEL[status]}</span>

export const Problem = ({ text }: { text: string }) => text ? <p className="problem" role="alert">{text}</p> : null
