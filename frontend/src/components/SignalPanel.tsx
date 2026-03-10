import { useQuery } from '@tanstack/react-query'
import { fetchSignals, type SignalEntry } from '../api/client'
import { useMarket } from '../contexts/MarketContext'

function SignalRow({ s }: { s: SignalEntry }) {
  const isBuy = s.signal === 'BUY'
  const color = isBuy ? 'text-green-400' : 'text-red-400'
  const bg = isBuy ? 'bg-green-900/20' : 'bg-red-900/20'
  const ts = new Date(s.timestamp)
  const time = ts.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  const date = ts.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' })

  return (
    <tr className={`${bg} border-b border-gray-800/50`}>
      <td className="px-3 py-2 text-xs text-gray-400">{date} {time}</td>
      <td className="px-3 py-2 text-sm font-mono font-medium text-white">{s.symbol}</td>
      <td className={`px-3 py-2 text-sm font-bold ${color}`}>{s.signal}</td>
      <td className="px-3 py-2 text-sm text-gray-300">{(s.confidence * 100).toFixed(0)}%</td>
      <td className="px-3 py-2 text-xs text-gray-400">{s.strategy}</td>
      <td className="px-3 py-2 text-xs text-gray-500">{s.market_state}</td>
      <td className="px-3 py-2 text-xs text-gray-500">{s.market}</td>
    </tr>
  )
}

export default function SignalPanel() {
  const { market } = useMarket()
  const { data: signals, isLoading } = useQuery({
    queryKey: ['signals', market],
    queryFn: () => fetchSignals(market, 100),
    refetchInterval: 30_000,
  })

  if (isLoading) return <div className="text-gray-500">Loading signals...</div>
  if (!signals || signals.length === 0) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 text-center text-gray-500">
        No signals yet. Signals appear when the evaluation loop runs during market hours.
      </div>
    )
  }

  const buys = signals.filter(s => s.signal === 'BUY').length
  const sells = signals.filter(s => s.signal === 'SELL').length

  return (
    <div className="space-y-4">
      <div className="flex gap-4 text-sm">
        <span className="text-gray-400">Total: <span className="text-white font-medium">{signals.length}</span></span>
        <span className="text-green-400">BUY: {buys}</span>
        <span className="text-red-400">SELL: {sells}</span>
      </div>

      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-800/50 text-gray-400 text-xs uppercase">
              <th className="px-3 py-2 text-left">Time</th>
              <th className="px-3 py-2 text-left">Symbol</th>
              <th className="px-3 py-2 text-left">Signal</th>
              <th className="px-3 py-2 text-left">Conf</th>
              <th className="px-3 py-2 text-left">Strategy</th>
              <th className="px-3 py-2 text-left">Regime</th>
              <th className="px-3 py-2 text-left">Mkt</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s, i) => <SignalRow key={i} s={s} />)}
          </tbody>
        </table>
      </div>
    </div>
  )
}
