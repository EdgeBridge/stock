import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  RefreshControl,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import {
  fetchPortfolioSummary,
  fetchPositions,
  fetchPortfolioReturns,
  fetchTradeSummaryPeriods,
  fetchEngineStatus,
  fetchMarketState,
  fetchMacroIndicators,
} from '../api/client'
import type {
  PortfolioSummary,
  Position,
  PortfolioReturns,
  TradeSummaryPeriods,
  PeriodSummary,
  EngineStatus,
  MarketState,
  MacroIndicators,
} from '../types'
import { colors, pnlColor, phaseColor } from '../utils/colors'
import { formatCurrency, formatPnl } from '../utils/format'
import {
  MarketPill,
  MktTag,
  PctBadge,
  PnlText,
  StatCard,
  InfoRow,
  SectionCard,
} from '../components/SharedComponents'

/* ─── Constants ─── */

const REFRESH_INTERVAL = 60_000
type ReturnPeriod = 'daily' | 'weekly' | 'monthly'
const PERIOD_LABELS: Record<ReturnPeriod, string> = { daily: '1D', weekly: '1W', monthly: '1M' }
const PERIOD_KEYS: ReturnPeriod[] = ['daily', 'weekly', 'monthly']

/* ─── Props ─── */

interface Props {
  onSettingsPress: () => void
}

/* ─── Main Component ─── */

export default function DashboardScreen({ onSettingsPress }: Props) {
  // Data state
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [positions, setPositions] = useState<Position[] | null>(null)
  const [returns, setReturns] = useState<PortfolioReturns | null>(null)
  const [usTradeSummary, setUsTradeSummary] = useState<TradeSummaryPeriods | null>(null)
  const [krTradeSummary, setKrTradeSummary] = useState<TradeSummaryPeriods | null>(null)
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null)
  const [marketState, setMarketState] = useState<MarketState | null>(null)
  const [macro, setMacro] = useState<MacroIndicators | null>(null)

  // UI state
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [returnPeriod, setReturnPeriod] = useState<ReturnPeriod>('daily')

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [
        summaryRes,
        positionsRes,
        returnsRes,
        usTradeRes,
        krTradeRes,
        engineRes,
        marketRes,
        macroRes,
      ] = await Promise.all([
        fetchPortfolioSummary('ALL'),
        fetchPositions('ALL'),
        fetchPortfolioReturns(),
        fetchTradeSummaryPeriods('US').catch(() => null),
        fetchTradeSummaryPeriods('KR').catch(() => null),
        fetchEngineStatus(),
        fetchMarketState().catch(() => null),
        fetchMacroIndicators().catch(() => null),
      ])

      setSummary(summaryRes)
      setPositions(positionsRes)
      setReturns(returnsRes)
      setUsTradeSummary(usTradeRes)
      setKrTradeSummary(krTradeRes)
      setEngineStatus(engineRes)
      setMarketState(marketRes)
      setMacro(macroRes)
      setError(null)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load dashboard data'
      setError(msg)
    }
  }, [])

  // Initial load
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      await fetchAll()
      if (!cancelled) setLoading(false)
    })()
    return () => { cancelled = true }
  }, [fetchAll])

  // Auto-refresh every 60s
  useEffect(() => {
    intervalRef.current = setInterval(fetchAll, REFRESH_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchAll])

  // Pull-to-refresh
  const onRefresh = useCallback(async () => {
    setRefreshing(true)
    await fetchAll()
    setRefreshing(false)
  }, [fetchAll])

  // Derived values
  const usPhase = engineStatus?.market_phase ?? 'closed'
  const krPhase = engineStatus?.kr_market_phase ?? 'closed'
  const usActive = usPhase === 'regular'
  const krActive = krPhase === 'regular'

  const sortedPositions = useMemo(() => {
    if (!positions) return []
    return [...positions].sort((a, b) => {
      const aMkt = a.market ?? 'US'
      const bMkt = b.market ?? 'US'
      const aActive = (aMkt === 'KR' && krActive) || (aMkt === 'US' && usActive)
      const bActive = (bMkt === 'KR' && krActive) || (bMkt === 'US' && usActive)
      if (aActive !== bActive) return aActive ? -1 : 1
      return Math.abs(b.unrealized_pnl ?? 0) - Math.abs(a.unrealized_pnl ?? 0)
    })
  }, [positions, usActive, krActive])

  const totalEquity = summary
    ? summary.total_equity ??
      (summary.balance.total + (summary.usd_balance?.total ?? 0) * (summary.exchange_rate ?? 1450))
    : 0
  const rate = summary?.exchange_rate ?? 1450
  const hasUsd = (summary?.usd_balance?.total ?? 0) > 0

  // Loading state
  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.gray400} />
        <Text style={styles.loadingText}>Loading dashboard...</Text>
      </View>
    )
  }

  // Error state
  if (error && !summary) {
    return (
      <View style={styles.center}>
        <Ionicons name="cloud-offline-outline" size={48} color={colors.gray400} />
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={onRefresh} activeOpacity={0.7}>
          <Text style={styles.retryButtonText}>Retry</Text>
        </TouchableOpacity>
      </View>
    )
  }

  const selectedReturn = returns?.[returnPeriod] ?? null

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={styles.scrollContent}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.gray400} />
      }
      showsVerticalScrollIndicator={false}
    >
      {/* Header row: MarketPills + Settings */}
      <View style={styles.headerRow}>
        <View style={styles.pillRow}>
          <MarketPill label="US" phase={usPhase} />
          <MarketPill label="KR" phase={krPhase} />
        </View>
        <TouchableOpacity
          onPress={onSettingsPress}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <Ionicons name="settings-outline" size={22} color={colors.gray500} />
        </TouchableOpacity>
      </View>

      {/* Equity Hero Card */}
      <View style={styles.equityCard}>
        <Text style={styles.equityLabel}>Total Equity</Text>
        <Text style={styles.equityValue}>{formatCurrency(totalEquity, 'KRW')}</Text>

        {hasUsd && summary && (
          <Text style={styles.equityBreakdown}>
            KRW {formatCurrency(summary.balance.total, 'KRW')}
            {'  '}USD {formatCurrency(summary.usd_balance!.total, 'USD')}
            {'  '}{'\u20A9'}{rate.toFixed(0)}
          </Text>
        )}

        {returns && (
          <View style={styles.returnSection}>
            <View style={styles.returnDivider} />

            {/* Period picker */}
            <View style={styles.periodRow}>
              {PERIOD_KEYS.map((p) => {
                const active = returnPeriod === p
                return (
                  <TouchableOpacity
                    key={p}
                    style={[styles.periodButton, active && styles.periodButtonActive]}
                    onPress={() => setReturnPeriod(p)}
                    activeOpacity={0.7}
                  >
                    <Text style={[styles.periodText, active && styles.periodTextActive]}>
                      {PERIOD_LABELS[p]}
                    </Text>
                  </TouchableOpacity>
                )
              })}
            </View>

            {/* Return value */}
            {selectedReturn ? (
              <View style={styles.returnValueRow}>
                <Text
                  style={[
                    styles.returnChange,
                    { color: pnlColor(selectedReturn.change) },
                  ]}
                >
                  {formatPnl(selectedReturn.change, 'KRW')}
                </Text>
                <PctBadge value={selectedReturn.pct} />
                {selectedReturn.has_cash_flows && (
                  <View style={styles.twrBadge}>
                    <Text style={styles.twrText}>TWR</Text>
                  </View>
                )}
              </View>
            ) : (
              <Text style={styles.noDataText}>No data yet</Text>
            )}
          </View>
        )}
      </View>

      {/* Quick Stats row */}
      {summary && (
        <View style={styles.statsRow}>
          <StatCard
            label="Cash"
            value={formatCurrency(
              summary.available_cash ?? summary.balance.available,
              'KRW',
            )}
          />
          <StatCard label="Positions" value={String(summary.positions_count)} />
          <StatCard
            label="Unrealized"
            value={
              <Text style={{ color: pnlColor(summary.total_unrealized_pnl), fontSize: 14, fontWeight: '700' }}>
                {formatPnl(summary.total_unrealized_pnl, 'KRW')}
              </Text>
            }
            sub={
              summary.total_unrealized_pnl_pct != null ? (
                <PctBadge value={summary.total_unrealized_pnl_pct} />
              ) : undefined
            }
          />
        </View>
      )}

      {/* Realized P&L 2x2 grid */}
      {(usTradeSummary || krTradeSummary) && (
        <View style={styles.pnlGrid}>
          <View style={styles.pnlGridRow}>
            <PnLCard label="Today" us={usTradeSummary?.today} kr={krTradeSummary?.today} />
            <PnLCard label="Week" us={usTradeSummary?.week} kr={krTradeSummary?.week} />
          </View>
          <View style={styles.pnlGridRow}>
            <PnLCard label="Month" us={usTradeSummary?.month} kr={krTradeSummary?.month} />
            <PnLCard label="All" us={usTradeSummary?.all_time} kr={krTradeSummary?.all_time} />
          </View>
        </View>
      )}

      {/* Holdings list */}
      {sortedPositions.length > 0 && (
        <SectionCard title="Holdings">
          {sortedPositions.map((p, idx) => {
            const mkt = p.market ?? 'US'
            const cur = mkt === 'KR' ? 'KRW' : 'USD'
            const pnl = p.unrealized_pnl ?? (p.current_price - p.avg_price) * p.quantity
            const pnlPct =
              p.unrealized_pnl_pct ??
              (p.avg_price > 0
                ? ((p.current_price - p.avg_price) / p.avg_price) * 100
                : 0)
            const isActive = (mkt === 'KR' && krActive) || (mkt === 'US' && usActive)
            const slPct = p.stop_loss_pct ?? 0.08
            const tpPct = p.take_profit_pct ?? 0.20
            const isLast = idx === sortedPositions.length - 1

            return (
              <View
                key={p.symbol}
                style={[
                  styles.holdingItem,
                  !isLast && styles.holdingBorder,
                  !isActive && styles.holdingInactive,
                ]}
              >
                {/* Top row: symbol + P&L */}
                <View style={styles.holdingTopRow}>
                  <View style={styles.holdingSymbolRow}>
                    <MktTag mkt={mkt} />
                    <Text style={styles.holdingSymbol}>{p.symbol}</Text>
                    {p.trailing_active && (
                      <View style={styles.trailingBadge}>
                        <Text style={styles.trailingText}>T</Text>
                      </View>
                    )}
                  </View>
                  <View style={styles.holdingPnlCol}>
                    <Text style={[styles.holdingPnl, { color: pnlColor(pnl) }]}>
                      {formatPnl(pnl, cur)}
                    </Text>
                    <PctBadge value={pnlPct} />
                  </View>
                </View>

                {/* Bottom row: quantity + SL/TP */}
                <View style={styles.holdingBottomRow}>
                  <Text style={styles.holdingMeta}>
                    {p.quantity}주 · avg {formatCurrency(p.avg_price, cur)}
                  </Text>
                  <Text style={styles.holdingMeta}>
                    SL{' '}
                    <Text style={{ color: colors.rose600 }}>
                      -{(slPct * 100).toFixed(0)}%
                    </Text>
                    {' / TP '}
                    <Text style={{ color: colors.emerald600 }}>
                      +{(tpPct * 100).toFixed(0)}%
                    </Text>
                  </Text>
                </View>
              </View>
            )
          })}
        </SectionCard>
      )}

      {/* Market & Macro — side by side */}
      <View style={styles.marketMacroRow}>
        {/* Market State */}
        <View style={styles.marketMacroCard}>
          <SectionCard title="Market">
            {marketState ? (
              <View style={styles.infoGrid}>
                <InfoRow
                  label="US"
                  value={marketState.market_phase ?? '-'}
                  color={phaseColor(marketState.market_phase ?? '')}
                />
                <InfoRow label="Regime" value={marketState.regime ?? '-'} />
                <InfoRow
                  label="SPY"
                  value={
                    marketState.spy_price != null
                      ? `$${Number(marketState.spy_price).toFixed(2)}`
                      : '-'
                  }
                />
                <InfoRow
                  label="VIX"
                  value={
                    marketState.vix_level != null
                      ? Number(marketState.vix_level).toFixed(1)
                      : '-'
                  }
                />
                <View style={styles.infoDivider} />
                <InfoRow
                  label="KR"
                  value={marketState.kr_market_phase ?? '-'}
                  color={phaseColor(marketState.kr_market_phase ?? '')}
                />
                <InfoRow label="Regime" value={marketState.kr_regime ?? '-'} />
                {marketState.kr_index_price != null && (
                  <InfoRow
                    label="KODEX"
                    value={`\u20A9${Number(marketState.kr_index_price).toLocaleString()}`}
                  />
                )}
              </View>
            ) : (
              <Text style={styles.cardPlaceholder}>Loading...</Text>
            )}
          </SectionCard>
        </View>

        {/* Macro Indicators */}
        <View style={styles.marketMacroCard}>
          <SectionCard title="Macro">
            {macro ? (
              <View style={styles.infoGrid}>
                <InfoRow
                  label="Fed Rate"
                  value={
                    macro.fed_funds_rate != null
                      ? `${Number(macro.fed_funds_rate).toFixed(2)}%`
                      : '-'
                  }
                />
                <InfoRow
                  label="10Y"
                  value={
                    macro.treasury_10y != null
                      ? `${Number(macro.treasury_10y).toFixed(2)}%`
                      : '-'
                  }
                />
                <InfoRow
                  label="Spread"
                  value={
                    macro.yield_spread != null
                      ? `${Number(macro.yield_spread).toFixed(2)}%`
                      : '-'
                  }
                />
                <InfoRow
                  label="CPI"
                  value={
                    macro.cpi_yoy != null
                      ? `${Number(macro.cpi_yoy).toFixed(2)}%`
                      : '-'
                  }
                />
                <InfoRow
                  label="Unemp."
                  value={
                    macro.unemployment_rate != null
                      ? `${Number(macro.unemployment_rate).toFixed(1)}%`
                      : '-'
                  }
                />
              </View>
            ) : (
              <Text style={styles.cardPlaceholder}>Loading...</Text>
            )}
          </SectionCard>
        </View>
      </View>
    </ScrollView>
  )
}

/* ─── PnLCard sub-component ─── */

function PnLCard({
  label,
  us,
  kr,
}: {
  label: string
  us?: PeriodSummary
  kr?: PeriodSummary
}) {
  const hasKr = (kr?.trades ?? 0) > 0
  const hasUs = (us?.trades ?? 0) > 0

  return (
    <View style={pnlCardStyles.card}>
      <Text style={pnlCardStyles.label}>{label}</Text>
      {!hasKr && !hasUs ? (
        <Text style={pnlCardStyles.empty}>{'\u2014'}</Text>
      ) : (
        <View style={pnlCardStyles.lines}>
          {hasKr && (
            <PnLLine
              tag="KR"
              pnl={kr!.pnl}
              pnlPct={kr!.pnl_pct}
              currency="KRW"
              trades={kr!.trades}
              wins={kr!.wins}
              losses={kr!.losses}
            />
          )}
          {hasUs && (
            <PnLLine
              tag="US"
              pnl={us!.pnl}
              pnlPct={us!.pnl_pct}
              currency="USD"
              trades={us!.trades}
              wins={us!.wins}
              losses={us!.losses}
            />
          )}
        </View>
      )}
    </View>
  )
}

const pnlCardStyles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: colors.white,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.gray100,
    padding: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  label: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.gray400,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  empty: {
    fontSize: 14,
    color: colors.gray200,
  },
  lines: {
    gap: 6,
  },
})

/* ─── PnLLine sub-component ─── */

function PnLLine({
  tag,
  pnl,
  pnlPct,
  currency,
  trades,
  wins,
  losses,
}: {
  tag: string
  pnl: number
  pnlPct: number | null
  currency: string
  trades: number
  wins: number
  losses: number
}) {
  const isKR = tag === 'KR'
  const tagBg = isKR ? colors.violet100 : colors.sky100
  const tagFg = isKR ? colors.violet700 : colors.sky600

  return (
    <View>
      <View style={pnlLineStyles.topRow}>
        <View style={[pnlLineStyles.tag, { backgroundColor: tagBg }]}>
          <Text style={[pnlLineStyles.tagText, { color: tagFg }]}>{tag}</Text>
        </View>
        <Text style={[pnlLineStyles.pnlValue, { color: pnlColor(pnl) }]}>
          {formatPnl(pnl, currency)}
        </Text>
        <Text style={pnlLineStyles.tradeMeta}>
          {trades}T {wins}W/{losses}L
        </Text>
      </View>
      {pnlPct != null && (
        <View style={pnlLineStyles.pctRow}>
          <PctBadge value={pnlPct} />
        </View>
      )}
    </View>
  )
}

const pnlLineStyles = StyleSheet.create({
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  tag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 999,
  },
  tagText: {
    fontSize: 9,
    fontWeight: '700',
  },
  pnlValue: {
    fontSize: 13,
    fontWeight: '700',
    flexShrink: 1,
  },
  tradeMeta: {
    fontSize: 10,
    color: colors.gray400,
    marginLeft: 'auto',
  },
  pctRow: {
    marginLeft: 28,
    marginTop: 2,
  },
})

/* ─── Styles ─── */

const styles = StyleSheet.create({
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.gray50,
    padding: 24,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: colors.gray400,
  },
  errorText: {
    marginTop: 12,
    fontSize: 14,
    color: colors.gray500,
    textAlign: 'center',
    lineHeight: 20,
  },
  retryButton: {
    marginTop: 16,
    backgroundColor: colors.emerald600,
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 10,
  },
  retryButtonText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '600',
  },
  scrollView: {
    flex: 1,
    backgroundColor: colors.gray50,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 32,
  },

  /* Header */
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  pillRow: {
    flexDirection: 'row',
    gap: 8,
  },

  /* Equity Hero Card */
  equityCard: {
    backgroundColor: colors.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.gray100,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  equityLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.gray400,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  equityValue: {
    fontSize: 30,
    fontWeight: '800',
    color: colors.gray900,
    letterSpacing: -0.5,
    marginTop: 4,
  },
  equityBreakdown: {
    fontSize: 12,
    color: colors.gray400,
    marginTop: 4,
  },
  returnSection: {
    marginTop: 12,
  },
  returnDivider: {
    height: 1,
    backgroundColor: colors.gray100,
    marginBottom: 12,
  },
  periodRow: {
    flexDirection: 'row',
    gap: 4,
    marginBottom: 8,
  },
  periodButton: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
  },
  periodButtonActive: {
    backgroundColor: colors.gray900,
  },
  periodText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.gray400,
  },
  periodTextActive: {
    color: colors.white,
  },
  returnValueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  returnChange: {
    fontSize: 18,
    fontWeight: '700',
  },
  twrBadge: {
    backgroundColor: colors.amber50,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 999,
  },
  twrText: {
    fontSize: 9,
    fontWeight: '700',
    color: colors.amber600,
  },
  noDataText: {
    fontSize: 12,
    color: colors.gray200,
  },

  /* Quick Stats */
  statsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
  },

  /* Realized P&L grid */
  pnlGrid: {
    marginTop: 16,
    gap: 8,
  },
  pnlGridRow: {
    flexDirection: 'row',
    gap: 8,
  },

  /* Holdings */
  holdingItem: {
    paddingVertical: 12,
  },
  holdingBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.gray100,
  },
  holdingInactive: {
    opacity: 0.4,
  },
  holdingTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  holdingSymbolRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  holdingSymbol: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.gray900,
  },
  trailingBadge: {
    backgroundColor: colors.amber50,
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
  },
  trailingText: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.amber600,
  },
  holdingPnlCol: {
    alignItems: 'flex-end',
    gap: 2,
  },
  holdingPnl: {
    fontSize: 14,
    fontWeight: '700',
  },
  holdingBottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  holdingMeta: {
    fontSize: 11,
    color: colors.gray400,
  },

  /* Market & Macro side by side */
  marketMacroRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 16,
  },
  marketMacroCard: {
    flex: 1,
  },
  infoGrid: {
    gap: 4,
  },
  infoDivider: {
    height: 1,
    backgroundColor: colors.gray100,
    marginVertical: 6,
  },
  cardPlaceholder: {
    fontSize: 13,
    color: colors.gray200,
  },
})
