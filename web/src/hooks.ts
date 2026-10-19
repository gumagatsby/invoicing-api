import { useCallback, useEffect, useState } from 'react'
import { ApiError } from './api'

// Routes live in the hash (#/invoices/<id>), so a page can be linked and the Back button works.
export function useRoute() {
  const read = () => location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [route, setRoute] = useState(read)
  useEffect(() => {
    const on = () => setRoute(read())
    addEventListener('hashchange', on)
    return () => removeEventListener('hashchange', on)
  }, [])
  return route
}
export const go = (path: string) => { location.hash = '#/' + path }

// Loads data, reloads when `deps` change or `reload()` is called, and keeps the last error.
export function useLoad<T>(load: () => Promise<T>, deps: unknown[], onAuthLost: () => void) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps)
  useEffect(() => {
    let live = true
    run().then(d => { if (live) { setData(d); setError('') } }).catch(e => {
      if (!live) return
      if (e instanceof ApiError && e.status === 401) onAuthLost()
      else setError(e instanceof Error ? e.message : String(e))
    })
    return () => { live = false }
  }, [run, tick, onAuthLost])
  return { data, error, reload: () => setTick(t => t + 1) }
}
