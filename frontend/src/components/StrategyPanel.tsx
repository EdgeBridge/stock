import { useStrategies } from '../hooks/useApi'

export default function StrategyPanel() {
  const { data: strategies, isLoading } = useStrategies()

  if (isLoading) return <div className="text-gray-500">Loading strategies...</div>
  if (!strategies || strategies.length === 0) {
    return <div className="text-gray-500">No strategies loaded.</div>
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Active Strategies</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {strategies.map(s => (
          <div key={s.name} className="bg-gray-900 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium">{s.display_name}</h3>
              <span className="text-xs px-2 py-0.5 bg-blue-900 text-blue-300 rounded">
                {s.timeframe}
              </span>
            </div>
            <div className="text-xs text-gray-400 mb-3">
              {s.applicable_market_types.join(', ')}
            </div>
            <div className="space-y-1">
              {Object.entries(s.params).map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-gray-400">{k}</span>
                  <span className="text-gray-200">{String(v)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
