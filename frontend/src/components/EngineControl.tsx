import { useEngineStatus, useEngineControl } from '../hooks/useApi'
import { useMutation } from '@tanstack/react-query'
import { runEvaluation } from '../api/client'
import clsx from 'clsx'

const phaseBg: Record<string, string> = {
  regular: 'bg-emerald-100 text-emerald-700',
  pre_market: 'bg-sky-100 text-sky-700',
  after_hours: 'bg-amber-100 text-amber-700',
  closed: 'bg-gray-100 text-gray-500',
}

const phaseDot: Record<string, string> = {
  regular: 'bg-emerald-500',
  pre_market: 'bg-sky-500',
  after_hours: 'bg-amber-500',
  closed: 'bg-gray-400',
}

export default function EngineControl() {
  const { data: status } = useEngineStatus()
  const { start, stop } = useEngineControl()
  const evaluate = useMutation({ mutationFn: runEvaluation })

  const running = status?.running ?? false
  const usPhase = status?.market_phase ?? 'closed'
  const krPhase = status?.kr_market_phase ?? 'closed'

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Engine status + controls */}
      <div className="flex items-center gap-2">
        <div
          className={clsx(
            'w-2 h-2 rounded-full',
            running ? 'bg-emerald-500 animate-pulse' : 'bg-gray-400'
          )}
        />
        <span className="text-sm text-gray-600 font-medium">
          {running ? 'Running' : 'Stopped'}
        </span>
      </div>

      {running ? (
        <button
          onClick={() => stop.mutate()}
          disabled={stop.isPending}
          className="px-2.5 py-1 text-xs font-semibold bg-rose-500 hover:bg-rose-600 text-white rounded-lg transition disabled:opacity-50"
        >
          Stop
        </button>
      ) : (
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending}
          className="px-2.5 py-1 text-xs font-semibold bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg transition disabled:opacity-50"
        >
          Start
        </button>
      )}

      <button
        onClick={() => evaluate.mutate()}
        disabled={evaluate.isPending}
        className="px-2.5 py-1 text-xs font-semibold bg-amber-500 hover:bg-amber-600 text-white rounded-lg transition disabled:opacity-50"
      >
        {evaluate.isPending ? 'Eval...' : 'Evaluate'}
      </button>

      {/* Market phase pills — wrap to next line on mobile */}
      <span className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold',
        phaseBg[usPhase] ?? phaseBg.closed,
      )}>
        <span className={clsx('w-1.5 h-1.5 rounded-full', phaseDot[usPhase] ?? phaseDot.closed, usPhase === 'regular' && 'animate-pulse')} />
        US {usPhase.replace('_', ' ')}
      </span>

      <span className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold',
        phaseBg[krPhase] ?? phaseBg.closed,
      )}>
        <span className={clsx('w-1.5 h-1.5 rounded-full', phaseDot[krPhase] ?? phaseDot.closed, krPhase === 'regular' && 'animate-pulse')} />
        KR {krPhase.replace('_', ' ')}
      </span>
    </div>
  )
}
