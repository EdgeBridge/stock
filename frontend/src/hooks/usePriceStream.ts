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
  symbolsRef.current = symbols

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/api/v1/ws/prices`)

    ws.onopen = () => {
      setConnected(true)
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
      setTimeout(connect, 3000)
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
