import { useEffect, useRef, useState, useCallback } from 'react'

interface PriceUpdate {
  symbol: string
  price: number
  change_pct: number
  volume: number
}

export function usePriceStream(symbols: string[]) {
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const symbolsRef = useRef(symbols)
  const retryDelayRef = useRef(2000)
  symbolsRef.current = symbols

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/api/v1/ws/prices`)

    ws.onopen = () => {
      setConnected(true)
      retryDelayRef.current = 2000 // reset on success
      if (symbolsRef.current.length > 0) {
        ws.send(JSON.stringify({ subscribe: symbolsRef.current }))
      }
    }

    ws.onmessage = (e) => {
      try {
        const data: PriceUpdate = JSON.parse(e.data)
        setPrices(prev => ({ ...prev, [data.symbol]: data }))
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      setConnected(false)
      const delay = retryDelayRef.current
      retryDelayRef.current = Math.min(delay * 1.5, 30000)
      setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
    wsRef.current = ws
  }, [])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  // Re-subscribe when symbols change
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN && symbols.length > 0) {
      wsRef.current.send(JSON.stringify({ subscribe: symbols }))
    }
  }, [symbols])

  return { prices, connected }
}
