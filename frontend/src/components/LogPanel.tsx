import { useState, useEffect, useRef } from 'react'
import clsx from 'clsx'

interface LogEntry {
  timestamp: string
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'
  message: string
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-blue-400',
  WARN: 'text-yellow-400',
  ERROR: 'text-red-400',
  DEBUG: 'text-gray-500',
}

export default function LogPanel() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState<string>('ALL')
  const [connected, setConnected] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws/logs`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    ws.onmessage = (event) => {
      try {
        const entry: LogEntry = JSON.parse(event.data)
        setLogs(prev => [...prev.slice(-499), entry])
      } catch {
        // non-JSON messages — wrap as INFO
        setLogs(prev => [...prev.slice(-499), {
          timestamp: new Date().toISOString(),
          level: 'INFO',
          message: event.data,
        }])
      }
    }

    return () => { ws.close() }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const filtered = filter === 'ALL'
    ? logs
    : logs.filter(l => l.level === filter)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">System Log</h2>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className={clsx(
              'w-2 h-2 rounded-full',
              connected ? 'bg-green-500' : 'bg-red-500'
            )} />
            <span className="text-xs text-gray-400">
              {connected ? 'Live' : 'Disconnected'}
            </span>
          </div>

          <select
            value={filter}
            onChange={e => setFilter(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
          >
            <option value="ALL">All</option>
            <option value="INFO">Info</option>
            <option value="WARN">Warn</option>
            <option value="ERROR">Error</option>
            <option value="DEBUG">Debug</option>
          </select>

          <button
            onClick={() => setLogs([])}
            className="text-xs text-gray-400 hover:text-white"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="bg-gray-950 border border-gray-800 rounded-lg p-3 h-96 overflow-y-auto font-mono text-xs">
        {filtered.length === 0 ? (
          <div className="text-gray-600 text-center mt-8">
            {connected ? 'Waiting for log messages...' : 'Connect to see real-time logs.'}
          </div>
        ) : (
          filtered.map((entry, i) => (
            <div key={i} className="flex gap-2 py-0.5 hover:bg-gray-900/50">
              <span className="text-gray-600 shrink-0">
                {entry.timestamp.slice(11, 23)}
              </span>
              <span className={clsx('w-12 shrink-0 font-bold', LEVEL_COLORS[entry.level])}>
                {entry.level.padEnd(5)}
              </span>
              <span className="text-gray-300 break-all">{entry.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
