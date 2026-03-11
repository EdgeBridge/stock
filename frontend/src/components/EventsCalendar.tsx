import { useMarketEvents } from '../hooks/useApi'

function eventBadge(type: string) {
  const cls = type === 'FOMC'
    ? 'bg-red-900/60 text-red-300'
    : type === 'CPI'
      ? 'bg-yellow-900/60 text-yellow-300'
      : 'bg-blue-900/60 text-blue-300'
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>{type}</span>
}

function formatValue(v: number) {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
  return `$${v.toFixed(0)}`
}

export default function EventsCalendar() {
  const { data, isLoading } = useMarketEvents()

  if (isLoading) return <div className="text-gray-500">Loading events...</div>
  if (!data) return null

  const { earnings, macro, insider } = data
  const hasData = earnings.length > 0 || macro.length > 0 || insider.length > 0

  if (!hasData) {
    return (
      <div className="bg-gray-900 rounded-lg p-6 text-center">
        <p className="text-gray-500">No event data available. Refreshes daily pre-market.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Macro Events */}
      {macro.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-gray-300">Upcoming Macro Events</h3>
          <div className="space-y-2">
            {macro.map((e, i) => {
              const isToday = e.date === new Date().toISOString().slice(0, 10)
              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 py-1.5 px-2 rounded ${isToday ? 'bg-yellow-900/20 border border-yellow-800/50' : ''}`}
                >
                  <span className="text-xs text-gray-500 font-mono w-20">{e.date}</span>
                  {eventBadge(e.event_type)}
                  <span className="text-sm text-gray-300">{e.description}</span>
                  {isToday && <span className="text-[10px] text-yellow-400 font-medium ml-auto">TODAY</span>}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Earnings Calendar */}
      {earnings.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-gray-300">Upcoming Earnings</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[400px]">
              <thead className="text-gray-400 border-b border-gray-800">
                <tr>
                  <th className="text-left py-2">Symbol</th>
                  <th className="text-left py-2">Date</th>
                  <th className="text-center py-2">Timing</th>
                  <th className="text-right py-2">EPS Est.</th>
                  <th className="text-right py-2">Rev Est.</th>
                </tr>
              </thead>
              <tbody>
                {earnings.map((e, i) => (
                  <tr key={i} className="border-b border-gray-800/50">
                    <td className="py-2 font-medium">{e.symbol}</td>
                    <td className="py-2 text-gray-400 font-mono text-xs">{e.date}</td>
                    <td className="py-2 text-center text-xs text-gray-500">
                      {e.hour === 'bmo' ? 'Before Open' : e.hour === 'amc' ? 'After Close' : e.hour || '-'}
                    </td>
                    <td className="py-2 text-right text-gray-300">
                      {e.eps_estimate != null ? `$${e.eps_estimate.toFixed(2)}` : '-'}
                    </td>
                    <td className="py-2 text-right text-gray-300">
                      {e.revenue_estimate != null ? formatValue(e.revenue_estimate) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Insider Activity */}
      {insider.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-semibold mb-3 text-gray-300">Notable Insider Activity</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[400px]">
              <thead className="text-gray-400 border-b border-gray-800">
                <tr>
                  <th className="text-left py-2">Symbol</th>
                  <th className="text-center py-2">Signal</th>
                  <th className="text-right py-2">Value</th>
                  <th className="text-right py-2">Txns</th>
                  <th className="text-left py-2">Key Insider</th>
                </tr>
              </thead>
              <tbody>
                {insider.map((t, i) => (
                  <tr key={i} className="border-b border-gray-800/50">
                    <td className="py-2 font-medium">{t.symbol}</td>
                    <td className="py-2 text-center">
                      <span className={`font-medium ${t.signal === 'BULLISH' ? 'text-green-400' : 'text-red-400'}`}>
                        {t.signal}
                      </span>
                    </td>
                    <td className="py-2 text-right text-gray-300">{formatValue(t.total_value)}</td>
                    <td className="py-2 text-right text-gray-400">{t.count}</td>
                    <td className="py-2 text-gray-400 text-xs truncate max-w-[150px]">
                      {t.top_buyer || t.top_seller || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
