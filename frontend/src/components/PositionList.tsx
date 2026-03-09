import { usePositions } from '../hooks/useApi'
import { useMarket } from '../contexts/MarketContext'
import { formatCurrency } from '../utils/format'

export default function PositionList() {
  const { market, currency } = useMarket()
  const { data: positions, isLoading } = usePositions(market)

  if (isLoading) return <div className="text-gray-500">Loading positions...</div>
  if (!positions || positions.length === 0) {
    return <div className="text-gray-500">No open positions.</div>
  }

  return (
    <div className="bg-gray-900 rounded-lg p-4">
      <h2 className="text-lg font-semibold mb-4">All Positions</h2>
      <table className="w-full text-sm">
        <thead className="text-gray-400 border-b border-gray-700">
          <tr>
            <th className="text-left py-2 px-3">Symbol</th>
            <th className="text-left py-2 px-3">Exchange</th>
            <th className="text-right py-2 px-3">Quantity</th>
            <th className="text-right py-2 px-3">Avg Price</th>
            <th className="text-right py-2 px-3">Current Price</th>
            <th className="text-right py-2 px-3">Value</th>
            <th className="text-right py-2 px-3">P&L</th>
            <th className="text-right py-2 px-3">P&L %</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const value = p.quantity * p.current_price
            const pnlColor = p.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
            return (
              <tr key={p.symbol} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="py-2 px-3 font-medium">{p.symbol}</td>
                <td className="py-2 px-3 text-gray-400">{p.exchange}</td>
                <td className="py-2 px-3 text-right">{p.quantity}</td>
                <td className="py-2 px-3 text-right">{formatCurrency(p.avg_price, currency)}</td>
                <td className="py-2 px-3 text-right">{formatCurrency(p.current_price, currency)}</td>
                <td className="py-2 px-3 text-right">{formatCurrency(value, currency)}</td>
                <td className={`py-2 px-3 text-right ${pnlColor}`}>
                  {p.unrealized_pnl >= 0 ? '+' : ''}{formatCurrency(p.unrealized_pnl, currency)}
                </td>
                <td className={`py-2 px-3 text-right ${pnlColor}`}>
                  {p.unrealized_pnl_pct >= 0 ? '+' : ''}{p.unrealized_pnl_pct.toFixed(2)}%
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
