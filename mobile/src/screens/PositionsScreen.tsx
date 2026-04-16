import React, { useState, useEffect, useCallback } from 'react'
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native'
import { colors, pnlColor } from '../utils/colors'
import { formatPnl, formatPct } from '../utils/format'
import { MktTag, PctBadge, SectionCard, InfoRow } from '../components/SharedComponents'
import { fetchPositions } from '../api/client'
import type { Position } from '../types'

const FILTERS = ['ALL', 'US', 'KR'] as const
type Filter = (typeof FILTERS)[number]

export default function PositionsScreen() {
  const [positions, setPositions] = useState<Position[]>([])
  const [filter, setFilter] = useState<Filter>('ALL')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true)
    try {
      const data = await fetchPositions(filter === 'ALL' ? undefined : filter)
      setPositions(data)
    } catch {
      // silently ignore — user can pull to refresh
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [filter])

  useEffect(() => {
    load(true)
  }, [load])

  const onRefresh = useCallback(() => {
    setRefreshing(true)
    load(false)
  }, [load])

  /* ── derived stats ── */
  const krPnl = positions.filter(p => (p.market ?? 'US') === 'KR').reduce((s, p) => s + p.unrealized_pnl, 0)
  const usPnl = positions.filter(p => (p.market ?? 'US') !== 'KR').reduce((s, p) => s + p.unrealized_pnl, 0)
  const totalPnlPct =
    positions.length > 0
      ? positions.reduce((sum, p) => sum + p.unrealized_pnl_pct, 0) / positions.length
      : 0
  const posCount = positions.length

  /* ── currency helper ── */
  const currencyFor = (p: Position) =>
    p.market === 'KR' || p.exchange === 'KRX' ? 'KRW' : 'USD'

  const marketFor = (p: Position) =>
    p.market ?? (p.exchange === 'KRX' ? 'KR' : 'US')

  /* ── render ── */

  const renderFilterChips = () => (
    <View style={styles.chipRow}>
      {FILTERS.map((f) => {
        const active = filter === f
        return (
          <TouchableOpacity
            key={f}
            style={[styles.chip, active && styles.chipActive]}
            onPress={() => setFilter(f)}
            activeOpacity={0.7}
          >
            <Text style={[styles.chipText, active && styles.chipTextActive]}>{f}</Text>
          </TouchableOpacity>
        )
      })}
    </View>
  )

  const renderSummary = () => (
    <View style={styles.summaryCard}>
      <View style={styles.summaryRow}>
        <View>
          <Text style={styles.summaryLabel}>Total P&L</Text>
          {usPnl !== 0 && (
            <Text style={[styles.summaryValue, { color: pnlColor(usPnl) }]}>
              {formatPnl(usPnl, 'USD')}
            </Text>
          )}
          {krPnl !== 0 && (
            <Text style={[styles.summaryValue, { color: pnlColor(krPnl) }]}>
              {formatPnl(krPnl, 'KRW')}
            </Text>
          )}
          {usPnl === 0 && krPnl === 0 && (
            <Text style={[styles.summaryValue, { color: colors.gray400 }]}>--</Text>
          )}
        </View>
        <View style={styles.summaryRight}>
          <PctBadge value={totalPnlPct} />
          <Text style={styles.posCount}>
            {posCount} position{posCount !== 1 ? 's' : ''}
          </Text>
        </View>
      </View>
    </View>
  )

  const renderPosition = ({ item }: { item: Position }) => {
    const mkt = marketFor(item)
    const currency = currencyFor(item)
    return (
      <View style={styles.posCard}>
        {/* top row: market tag + symbol + name */}
        <View style={styles.posTopRow}>
          <MktTag mkt={mkt} />
          <Text style={styles.posSymbol}>{item.symbol}</Text>
          {item.name != null && (
            <Text style={styles.posName} numberOfLines={1}>
              {item.name}
            </Text>
          )}
        </View>

        {/* P&L row */}
        <View style={styles.posPnlRow}>
          <Text style={[styles.posPnl, { color: pnlColor(item.unrealized_pnl) }]}>
            {formatPnl(item.unrealized_pnl, currency)}
          </Text>
          <PctBadge value={item.unrealized_pnl_pct} />
        </View>

        {/* details */}
        <View style={styles.posDetails}>
          <InfoRow label="Qty" value={item.quantity.toLocaleString()} />
          <InfoRow
            label="Avg Price"
            value={currency === 'USD'
              ? `$${item.avg_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : `${item.avg_price.toLocaleString('ko-KR')}원`}
          />
          <InfoRow
            label="Current"
            value={currency === 'USD'
              ? `$${item.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : `${item.current_price.toLocaleString('ko-KR')}원`}
          />
          {item.stop_loss_pct != null && (
            <InfoRow
              label="SL"
              value={formatPct(-Math.abs(item.stop_loss_pct))}
              color={colors.rose600}
            />
          )}
          {item.take_profit_pct != null && (
            <InfoRow
              label="TP"
              value={formatPct(item.take_profit_pct)}
              color={colors.emerald600}
            />
          )}
        </View>

        {/* trailing indicator */}
        {item.trailing_active && (
          <View style={styles.trailingBadge}>
            <Text style={styles.trailingText}>Trailing Active</Text>
          </View>
        )}
      </View>
    )
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.sky600} />
      </View>
    )
  }

  return (
    <View style={styles.container}>
      {renderFilterChips()}
      <FlatList
        data={positions}
        keyExtractor={(item) => `${marketFor(item)}-${item.symbol}`}
        renderItem={renderPosition}
        ListHeaderComponent={renderSummary}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No open positions</Text>
          </View>
        }
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.sky600} />
        }
        showsVerticalScrollIndicator={false}
      />
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.gray50,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.gray50,
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },

  /* filter chips */
  chipRow: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 4,
    backgroundColor: colors.gray50,
  },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.gray200,
  },
  chipActive: {
    backgroundColor: colors.sky600,
    borderColor: colors.sky600,
  },
  chipText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.gray500,
  },
  chipTextActive: {
    color: colors.white,
  },

  /* summary */
  summaryCard: {
    backgroundColor: colors.white,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: colors.gray100,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  summaryLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.gray400,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  summaryValue: {
    fontSize: 22,
    fontWeight: '800',
    marginTop: 2,
  },
  summaryRight: {
    alignItems: 'flex-end',
    gap: 4,
  },
  posCount: {
    fontSize: 12,
    color: colors.gray400,
    fontWeight: '500',
  },

  /* position card */
  posCard: {
    backgroundColor: colors.white,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: colors.gray100,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  posTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  posSymbol: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.gray900,
  },
  posName: {
    fontSize: 12,
    color: colors.gray400,
    flexShrink: 1,
  },
  posPnlRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  posPnl: {
    fontSize: 18,
    fontWeight: '800',
  },
  posDetails: {
    gap: 2,
  },
  trailingBadge: {
    marginTop: 8,
    alignSelf: 'flex-start',
    backgroundColor: colors.amber50,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  trailingText: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.amber600,
  },

  /* empty */
  emptyContainer: {
    alignItems: 'center',
    paddingTop: 48,
  },
  emptyText: {
    fontSize: 15,
    color: colors.gray400,
  },
})
