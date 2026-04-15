import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { usePortfolioSummary, usePositions, useEngineStatus, usePortfolioReturns } from '../hooks/useApi'
import { usePriceStream } from '../hooks/usePriceStream'
import { fetchMacroIndicators, fetchMarketState, fetchTradeSummaryPeriods } from '../api/client'
import type { PeriodReturn } from '../api/client'
import { formatCurrency } from '../utils/format'
import { useAccount, hexToRgba } from '../contexts/AccountContext'

function PnLText({ value, currency }: { value: number; currency: string }) {
  const color = value >= 0 ? 'text-emerald-500' : 'text-rose-500'
  const sign = value >= 0 ? '+' : ''
  return <span className={color}>{sign}{formatCurrency(value, currency)}</span>
}

function PctText({ value }: { value: number }) {
  const color = value >= 0 ? 'text-emerald-500' : 'text-rose-500'
  const sign = value >= 0 ? '+' : ''
  return <span className={color}>{sign}{value.toFixed(2)}%</span>
}

export default function Dashboard() {
  const { selectedAccountId, selectedAccount, accountColor } = useAccount()
  const { data: summary, isLoading } = usePortfolioSummary('ALL', selectedAccountId)
  const { data: positions } = usePositions('ALL', selectedAccountId)
  const { data: engineStatus } = useEngineStatus()
  const { data: returns } = usePortfolioReturns()
  const { data: usTradeSummary } = useQuery({
    queryKey: ['portfolio', 'trade-summary', 'US', selectedAccountId ?? 'all'],
    queryFn: () => fetchTradeSummaryPeriods('US', selectedAccountId),
    refetchInterval: 60_000,
  })
  const { data: krTradeSummary } = useQuery({
    queryKey: ['portfolio', 'trade-summary', 'KR', selectedAccountId ?? 'all'],
    queryFn: () => fetchTradeSummaryPeriods('KR', selectedAccountId),
    refetchInterval: 60_000,
  })
  const symbols = useMemo(
    () => (positions ?? []).map(p => p.symbol),
    [positions],
  )
  const { prices, connected } = usePriceStream(symbols)

  const usPhase = engineStatus?.market_phase ?? 'closed'
  const krPhase = engineStatus?.kr_market_phase ?? 'closed'
  const usActive = usPhase === 'regular'
  const krActive = krPhase === 'regular'

  const sortedPositions = useMemo(() => {
    if (!positions) return []
    return [...positions].sort((a, b) => {
      const aMkt = (a as { market?: string }).market ?? 'US'
      const bMkt = (b as { market?: string }).market ?? 'US'
      const aActive = (aMkt === 'KR' && krActive) || (aMkt === 'US' && usActive)
      const bActive = (bMkt === 'KR' && krActive) || (bMkt === 'US' && usActive)
      if (aActive !== bActive) return aActive ? -1 : 1
      return Math.abs(b.unrealized_pnl ?? 0) - Math.abs(a.unrealized_pnl ?? 0)
    })
  }, [positions, usActive, krActive])

  if (isLoading || !summary) {
    return <div className="flex items-center justify-center h-40 text-gray-400">Loading...</div>
  }

  const hasUsd = summary.usd_balance && summary.usd_balance.total > 0
  const rate = summary.exchange_rate ?? 1450
  const totalEquity = summary.total_equity ??
    (summary.balance.total + (summary.usd_balance?.total ?? 0) * rate)

  return (
    <div className="space-y-4 pb-8">
      {/* Market Status Bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <MarketPill label="US" phase={usPhase} />
        <MarketPill label="KR" phase={krPhase} />
        {connected && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-500">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live
          </span>
        )}
        {selectedAccount && (
          <span
            className="ml-auto text-[11px] px-2 py-0.5 rounded-full font-medium"
            style={{
              backgroundColor: hexToRgba(accountColor(selectedAccount.account_id), 0.15),
              color: accountColor(selectedAccount.account_id),
            }}
          >
            {selectedAccount.name}
          </span>
        )}
      </div>

      {/* Equity Hero */}
      <EquityCard
        totalEquity={totalEquity}
        hasUsd={!!hasUsd}
        krwTotal={summary.balance.total}
        usdTotal={summary.usd_balance?.total ?? 0}
        rate={rate}
        returns={returns}
      />

      {/* Quick Stats Row */}
      <div className="grid grid-cols-3 gap-3">
        <MiniCard
          label="Cash"
          value={formatCurrency(summary.available_cash ?? summary.balance.available, 'KRW')}
        />
        <MiniCard label="Positions" value={String(summary.positions_count)} />
        <MiniCard
          label="P&L"
          value={
            <span className={summary.total_unrealized_pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
              {summary.total_unrealized_pnl >= 0 ? '+' : ''}{formatCurrency(summary.total_unrealized_pnl, 'KRW')}
            </span>
          }
          sub={summary.total_unrealized_pnl_pct != null
            ? `${summary.total_unrealized_pnl_pct >= 0 ? '+' : ''}${summary.total_unrealized_pnl_pct.toFixed(1)}%`
            : undefined
          }
          subColor={summary.total_unrealized_pnl_pct != null && summary.total_unrealized_pnl_pct >= 0 ? 'text-emerald-500' : 'text-rose-500'}
        />
      </div>

      {/* Realized P&L */}
      {(usTradeSummary || krTradeSummary) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <PnLCard label="Today" us={usTradeSummary?.today} kr={krTradeSummary?.today} />
          <PnLCard label="Week" us={usTradeSummary?.week} kr={krTradeSummary?.week} />
          <PnLCard label="Month" us={usTradeSummary?.month} kr={krTradeSummary?.month} />
          <PnLCard label="All" us={usTradeSummary?.all_time} kr={krTradeSummary?.all_time} />
        </div>
      )}

      {/* Holdings */}
      {sortedPositions.length > 0 && (
        <div className="bg-gray-900/60 backdrop-blur rounded-2xl overflow-hidden">
          <div className="px-4 py-3 border-b border-white/5">
            <h2 className="text-sm font-semibold text-gray-200">Holdings</h2>
          </div>

          {/* Mobile card view */}
          <div className="divide-y divide-white/5 md:hidden">
            {sortedPositions.map(p => {
              const mkt = (p as { market?: string }).market ?? 'US'
              const cur = mkt === 'KR' ? 'KRW' : 'USD'
              const live = prices[p.symbol]
              const currentPrice = live?.price ?? p.current_price
              const pnl = (currentPrice - p.avg_price) * p.quantity
              const pnlPct = p.avg_price > 0
                ? ((currentPrice - p.avg_price) / p.avg_price) * 100
                : 0
              const isActive = (mkt === 'KR' && krActive) || (mkt === 'US' && usActive)
              const ext = p as { stop_loss_pct?: number; take_profit_pct?: number; trailing_active?: boolean }
              return (
                <div key={p.symbol} className={`px-4 py-3 ${isActive ? '' : 'opacity-50'}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        mkt === 'KR' ? 'bg-violet-500/15 text-violet-400' : 'bg-sky-500/15 text-sky-400'
                      }`}>{mkt}</span>
                      <span className="font-semibold text-sm text-white">{p.symbol}</span>
                      {ext.trailing_active && <span className="text-[10px] text-amber-400">T</span>}
                    </div>
                    <div className="text-right">
                      <div className={`text-sm font-semibold ${pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                        {pnl >= 0 ? '+' : ''}{formatCurrency(pnl, cur)}
                      </div>
                      <div className={`text-[11px] ${pnlPct >= 0 ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-1.5 text-[11px] text-gray-500">
                    <span>{p.quantity}주 @ {formatCurrency(p.avg_price, cur)}</span>
                    <span>
                      <span className="text-rose-400/50">SL -{((ext.stop_loss_pct ?? 0.08) * 100).toFixed(0)}%</span>
                      {' · '}
                      <span className="text-emerald-400/50">TP +{((ext.take_profit_pct ?? 0.20) * 100).toFixed(0)}%</span>
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Desktop table view */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-gray-500 text-xs">
                <tr className="border-b border-white/5">
                  <th className="text-left py-2.5 px-4 font-medium">Symbol</th>
                  <th className="text-center py-2.5 font-medium">Mkt</th>
                  <th className="text-right py-2.5 font-medium">Qty</th>
                  <th className="text-right py-2.5 font-medium">Avg</th>
                  <th className="text-right py-2.5 font-medium">Now</th>
                  <th className="text-right py-2.5 font-medium">P&L</th>
                  <th className="text-right py-2.5 font-medium">%</th>
                  <th className="text-right py-2.5 px-4 font-medium">SL / TP</th>
                </tr>
              </thead>
              <tbody>
                {sortedPositions.map(p => {
                  const mkt = (p as { market?: string }).market ?? 'US'
                  const cur = mkt === 'KR' ? 'KRW' : 'USD'
                  const live = prices[p.symbol]
                  const currentPrice = live?.price ?? p.current_price
                  const pnl = (currentPrice - p.avg_price) * p.quantity
                  const pnlPct = p.avg_price > 0
                    ? ((currentPrice - p.avg_price) / p.avg_price) * 100
                    : 0
                  const isActive = (mkt === 'KR' && krActive) || (mkt === 'US' && usActive)
                  const ext = p as { stop_loss_pct?: number; take_profit_pct?: number; trailing_active?: boolean }
                  const slPct = ext.stop_loss_pct ?? 0.08
                  const tpPct = ext.take_profit_pct ?? 0.20
                  return (
                    <tr key={p.symbol} className={`border-b border-white/5 hover:bg-white/[0.02] transition ${isActive ? '' : 'opacity-50'}`}>
                      <td className="py-2.5 px-4">
                        <span className="font-medium">{p.symbol}</span>
                        {p.name && <span className="text-gray-600 text-xs ml-1.5 hidden lg:inline">{p.name}</span>}
                      </td>
                      <td className="text-center">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                          mkt === 'KR' ? 'bg-violet-500/15 text-violet-400' : 'bg-sky-500/15 text-sky-400'
                        }`}>{mkt}</span>
                      </td>
                      <td className="text-right tabular-nums">{p.quantity}</td>
                      <td className="text-right tabular-nums">{formatCurrency(p.avg_price, cur)}</td>
                      <td className="text-right tabular-nums">{formatCurrency(currentPrice, cur)}</td>
                      <td className="text-right"><PnLText value={pnl} currency={cur} /></td>
                      <td className="text-right"><PctText value={pnlPct} /></td>
                      <td className="text-right px-4 text-xs text-gray-600">
                        <span className="text-rose-400/60">-{(slPct * 100).toFixed(0)}%</span>
                        {' / '}
                        <span className="text-emerald-400/60">+{(tpPct * 100).toFixed(0)}%</span>
                        {ext.trailing_active && <span className="ml-1 text-amber-400/70">T</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Market & Macro */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <MarketStateCard />
        <MacroIndicatorsCard />
      </div>
    </div>
  )
}

/* ─── Sub-components ─── */

function MarketPill({ label, phase }: { label: string; phase: string }) {
  const isOpen = phase === 'regular'
  const isPre = phase === 'pre_market'
  const isAfter = phase === 'after_hours'

  const bg = isOpen ? 'bg-emerald-500/10' : isPre ? 'bg-sky-500/10' : isAfter ? 'bg-amber-500/10' : 'bg-gray-800'
  const text = isOpen ? 'text-emerald-500' : isPre ? 'text-sky-400' : isAfter ? 'text-amber-400' : 'text-gray-500'
  const dot = isOpen ? 'bg-emerald-500' : isPre ? 'bg-sky-400' : isAfter ? 'bg-amber-400' : 'bg-gray-600'
  const phaseLabel = isOpen ? 'Open' : isPre ? 'Pre' : isAfter ? 'After' : 'Closed'

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${bg} ${text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot} ${isOpen ? 'animate-pulse' : ''}`} />
      {label} {phaseLabel}
    </span>
  )
}

type ReturnPeriod = 'daily' | 'weekly' | 'monthly'

function EquityCard({
  totalEquity, hasUsd, krwTotal, usdTotal, rate, returns,
}: {
  totalEquity: number; hasUsd: boolean; krwTotal: number; usdTotal: number; rate: number
  returns?: { daily: PeriodReturn | null; weekly: PeriodReturn | null; monthly: PeriodReturn | null }
}) {
  const [period, setPeriod] = useState<ReturnPeriod>('daily')
  const labels: Record<ReturnPeriod, string> = { daily: '1D', weekly: '1W', monthly: '1M' }
  const ret = returns?.[period] ?? null

  return (
    <div className="bg-gray-900/60 backdrop-blur rounded-2xl p-5">
      <div className="text-xs text-gray-500 font-medium mb-1">Total Equity</div>
      <div className="text-3xl font-bold tracking-tight">{formatCurrency(totalEquity, 'KRW')}</div>
      {hasUsd && (
        <div className="text-xs text-gray-600 mt-0.5">
          KRW {formatCurrency(krwTotal, 'KRW')} · USD {formatCurrency(usdTotal, 'USD')} · {'\u20A9'}{rate.toFixed(0)}
        </div>
      )}
      {returns && (
        <div className="mt-3 pt-3 border-t border-white/5">
          <div className="flex items-center gap-1 mb-1.5">
            {(['daily', 'weekly', 'monthly'] as ReturnPeriod[]).map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-2 py-0.5 text-[11px] rounded-full font-medium transition ${
                  period === p
                    ? 'bg-white/10 text-white'
                    : 'text-gray-600 hover:text-gray-400'
                }`}
              >
                {labels[p]}
              </button>
            ))}
          </div>
          {ret ? (
            <div className="flex items-baseline gap-2">
              <span className={`text-lg font-bold ${ret.change >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                {ret.change >= 0 ? '+' : ''}{formatCurrency(ret.change, 'KRW')}
              </span>
              <span className={`text-xs font-medium ${ret.pct >= 0 ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>
                {ret.pct >= 0 ? '+' : ''}{ret.pct.toFixed(2)}%
              </span>
              {ret.has_cash_flows && (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 font-medium">TWR</span>
              )}
            </div>
          ) : (
            <div className="text-xs text-gray-700">No data yet</div>
          )}
        </div>
      )}
    </div>
  )
}

function MiniCard({ label, value, sub, subColor }: { label: string; value: React.ReactNode; sub?: string; subColor?: string }) {
  return (
    <div className="bg-gray-900/60 backdrop-blur rounded-xl px-3 py-2.5">
      <div className="text-[10px] text-gray-500 font-medium uppercase tracking-wider">{label}</div>
      <div className="text-base font-bold mt-0.5 truncate">{value}</div>
      {sub && <div className={`text-[10px] mt-0.5 ${subColor ?? 'text-gray-500'}`}>{sub}</div>}
    </div>
  )
}

function MarketStateCard() {
  const { data: marketState, isLoading } = useQuery({
    queryKey: ['engine', 'market-state'],
    queryFn: fetchMarketState,
    refetchInterval: 60_000,
  })

  return (
    <div className="bg-gray-900/60 backdrop-blur rounded-2xl p-4">
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Market State</h2>
      {isLoading && <p className="text-gray-600 text-sm">Loading...</p>}
      {marketState && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <StatRow label="US Phase" value={marketState.market_phase ?? '-'} color={phaseColor(marketState.market_phase ?? '')} />
            <StatRow label="Regime" value={marketState.regime ?? '-'} />
            <StatRow label="SPY" value={marketState.spy_price != null ? `$${Number(marketState.spy_price).toFixed(2)}` : '-'} />
            <StatRow label="VIX" value={marketState.vix_level != null ? Number(marketState.vix_level).toFixed(1) : '-'} />
          </div>
          <div className="border-t border-white/5 pt-3">
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <StatRow label="KR Phase" value={marketState.kr_market_phase ?? '-'} color={phaseColor(marketState.kr_market_phase ?? '')} />
              <StatRow label="KR Regime" value={marketState.kr_regime ?? '-'} />
              {marketState.kr_index_price != null && (
                <StatRow label="KODEX 200" value={`₩${Number(marketState.kr_index_price).toLocaleString()}`} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[10px] text-gray-600">{label}</div>
      <div className={`font-medium ${color ?? 'text-gray-200'}`}>{value}</div>
    </div>
  )
}

function phaseColor(phase: string) {
  if (phase === 'regular') return 'text-emerald-400'
  if (phase === 'pre_market') return 'text-sky-400'
  if (phase === 'after_hours') return 'text-amber-400'
  return 'text-gray-500'
}

function MacroIndicatorsCard() {
  const { data: macro, isLoading } = useQuery({
    queryKey: ['engine', 'macro'],
    queryFn: fetchMacroIndicators,
    refetchInterval: 60_000,
  })

  return (
    <div className="bg-gray-900/60 backdrop-blur rounded-2xl p-4">
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Macro</h2>
      {isLoading && <p className="text-gray-600 text-sm">Loading...</p>}
      {macro && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <StatRow label="Fed Rate" value={macro.fed_funds_rate != null ? `${Number(macro.fed_funds_rate).toFixed(2)}%` : '-'} />
          <StatRow label="10Y Yield" value={macro.treasury_10y != null ? `${Number(macro.treasury_10y).toFixed(2)}%` : '-'} />
          <StatRow label="Spread" value={macro.yield_spread != null ? `${Number(macro.yield_spread).toFixed(2)}%` : '-'} />
          <StatRow label="CPI YoY" value={macro.cpi_yoy != null ? `${Number(macro.cpi_yoy).toFixed(2)}%` : '-'} />
          <StatRow label="Unemployment" value={macro.unemployment_rate != null ? `${Number(macro.unemployment_rate).toFixed(1)}%` : '-'} />
        </div>
      )}
    </div>
  )
}

interface PeriodData { pnl: number; pnl_pct: number | null; trades: number; wins: number; losses: number; win_rate: number }

function PnLCard({ label, us, kr }: { label: string; us?: PeriodData; kr?: PeriodData }) {
  const hasKr = (kr?.trades ?? 0) > 0
  const hasUs = (us?.trades ?? 0) > 0

  return (
    <div className="bg-gray-900/60 backdrop-blur rounded-xl p-3">
      <div className="text-[10px] text-gray-500 font-medium uppercase tracking-wider mb-1.5">{label}</div>
      {!hasKr && !hasUs ? (
        <div className="text-sm text-gray-700">—</div>
      ) : (
        <div className="space-y-1.5">
          {hasKr && (
            <PnLLine
              tag="KR" tagColor="text-violet-400 bg-violet-500/10"
              pnl={kr!.pnl} pnlPct={kr!.pnl_pct} currency="KRW"
              trades={kr!.trades} wins={kr!.wins} losses={kr!.losses}
            />
          )}
          {hasUs && (
            <PnLLine
              tag="US" tagColor="text-sky-400 bg-sky-500/10"
              pnl={us!.pnl} pnlPct={us!.pnl_pct} currency="USD"
              trades={us!.trades} wins={us!.wins} losses={us!.losses}
            />
          )}
        </div>
      )}
    </div>
  )
}

function PnLLine({ tag, tagColor, pnl, pnlPct, currency, trades, wins, losses }: {
  tag: string; tagColor: string
  pnl: number; pnlPct?: number | null; currency: string
  trades: number; wins: number; losses: number
}) {
  const color = pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <span className={`text-[9px] px-1 py-0.5 rounded-full font-medium ${tagColor}`}>{tag}</span>
        <span className={`text-sm font-bold ${color}`}>
          {pnl >= 0 ? '+' : ''}{formatCurrency(pnl, currency)}
        </span>
        <span className="text-[10px] text-gray-600 ml-auto">{trades}T {wins}W/{losses}L</span>
      </div>
      {pnlPct != null && (
        <div className={`text-[10px] ml-6 ${pnlPct >= 0 ? 'text-emerald-500/60' : 'text-rose-500/60'}`}>
          {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
        </div>
      )}
    </div>
  )
}
