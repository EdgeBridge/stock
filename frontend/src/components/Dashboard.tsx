import { useMemo } from 'react'
import { usePortfolioSummary, usePositions } from '../hooks/useApi'
import { usePriceStream } from '../hooks/usePriceStream'

function formatUSD(n: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(n)
}

function PnLText({ value }: { value: number }) {
  const color = value >= 0 ? 'text-green-400' : 'text-red-400'
  const sign = value >= 0 ? '+' : ''
  return <span className={color}>{sign}{formatUSD(value)}</span>
}

export default function Dashboard() {
  const { data: summary, isLoading } = usePortfolioSummary()
  const { data: positions } = usePositions()
  const symbols = useMemo(
    () => (positions ?? []).map(p => p.symbol),
    [positions],
  )
  const { prices, connected } = usePriceStream(symbols)

  if (isLoading || !summary) {
    return <div className="text-gray-500">Loading...</div>
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card title="Total Equity" value={formatUSD(summary.total_equity)} />
        <Card title="Available Cash" value={formatUSD(summary.balance.available)} />
        <Card title="Positions" value={String(summary.positions_count)} />
        <Card
          title="Unrealized P&L"
          value={<PnLText value={summary.total_unrealized_pnl} />}
        />
      </div>

      {/* Top Positions */}
      {positions && positions.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">Holdings</h2>
            {connected && (
              <span className="text-xs text-green-500 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                Live
              </span>
            )}
          </div>
          <table className="w-full text-sm">
            <thead className="text-gray-400 border-b border-gray-800">
              <tr>
                <th className="text-left py-2">Symbol</th>
                <th className="text-right py-2">Qty</th>
                <th className="text-right py-2">Avg Price</th>
                <th className="text-right py-2">Current</th>
                <th className="text-right py-2">P&L</th>
                <th className="text-right py-2">P&L %</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => {
                const live = prices[p.symbol]
                const currentPrice = live?.price ?? p.current_price
                const pnl = (currentPrice - p.avg_price) * p.quantity
                const pnlPct = p.avg_price > 0
                  ? ((currentPrice - p.avg_price) / p.avg_price) * 100
                  : 0
                return (
                  <tr key={p.symbol} className="border-b border-gray-800/50">
                    <td className="py-2 font-medium">{p.symbol}</td>
                    <td className="text-right">{p.quantity}</td>
                    <td className="text-right">{formatUSD(p.avg_price)}</td>
                    <td className="text-right">{formatUSD(currentPrice)}</td>
                    <td className="text-right">
                      <PnLText value={pnl} />
                    </td>
                    <td className="text-right">
                      <PnLText value={pnlPct} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Card({ title, value }: { title: string; value: React.ReactNode }) {
  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <div className="text-xs text-gray-400 uppercase tracking-wide">{title}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  )
}
