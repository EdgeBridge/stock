import { useEngineStatus, useEngineControl } from '../hooks/useApi'
import clsx from 'clsx'

export default function EngineControl() {
  const { data: status } = useEngineStatus()
  const { start, stop } = useEngineControl()

  const running = status?.running ?? false

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        <div
          className={clsx(
            'w-2.5 h-2.5 rounded-full',
            running ? 'bg-green-500 animate-pulse' : 'bg-gray-600'
          )}
        />
        <span className="text-sm text-gray-300">
          {running ? 'Running' : 'Stopped'}
        </span>
      </div>

      {running ? (
        <button
          onClick={() => stop.mutate()}
          disabled={stop.isPending}
          className="px-3 py-1 text-xs font-medium bg-red-600 hover:bg-red-700 rounded transition-colors disabled:opacity-50"
        >
          Stop
        </button>
      ) : (
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending}
          className="px-3 py-1 text-xs font-medium bg-green-600 hover:bg-green-700 rounded transition-colors disabled:opacity-50"
        >
          Start
        </button>
      )}

      {status?.market_phase && (
        <span className="text-xs text-gray-500 uppercase">
          {status.market_phase.replace('_', ' ')}
        </span>
      )}
    </div>
  )
}
