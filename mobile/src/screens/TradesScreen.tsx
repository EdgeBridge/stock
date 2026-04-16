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
import { colors, pnlColor, pnlBg } from '../utils/colors'
import { formatPnl, formatPct, formatTimestamp } from '../utils/format'
import { MktTag, PctBadge } from '../components/SharedComponents'
import { fetchTrades } from '../api/client'
import type { Trade } from '../types'

const FILTERS = ['All', 'US', 'KR'] as const
type Filter = (typeof FILTERS)[number]

export default function TradesScreen() {
  const [trades, setTrades] = useState<Trade[]>([])
  const [filter, setFilter] = useState<Filter>('All')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true)
    try {
      const market = filter === 'All' ? undefined : filter
      const data = await fetchTrades({ limit: 100, market })
      setTrades(data)
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

  /* ── helpers ── */
  const currencyFor = (t: Trade) => (t.market === 'KR' ? 'KRW' : 'USD')
  const marketFor = (t: Trade) => t.market ?? 'US'

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

  const renderTrade = ({ item, index }: { item: Trade; index: number }) => {
    const mkt = marketFor(item)
    const currency = currencyFor(item)
    const isBuy = item.side.toUpperCase() === 'BUY'
    const effectivePrice = item.filled_price ?? item.price

    return (
      <View style={styles.tradeRow}>
        {/* left: market + side badge + symbol */}
        <View style={styles.tradeLeft}>
          <View style={styles.tradeTopRow}>
            <MktTag mkt={mkt} />
            <View style={[styles.sideBadge, { backgroundColor: isBuy ? colors.sky100 : colors.rose50 }]}>
              <Text style={[styles.sideText, { color: isBuy ? colors.sky600 : colors.rose600 }]}>
                {item.side.toUpperCase()}
              </Text>
            </View>
            <Text style={styles.tradeSymbol}>{item.symbol}</Text>
          </View>

          {/* quantity x price */}
          <Text style={styles.tradeQtyPrice}>
            {item.quantity.toLocaleString()} x{' '}
            {currency === 'USD'
              ? `$${effectivePrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : `${effectivePrice.toLocaleString('ko-KR')}원`}
          </Text>

          {/* strategy + timestamp */}
          <View style={styles.tradeMeta}>
            <Text style={styles.tradeStrategy} numberOfLines={1}>
              {item.strategy}
            </Text>
            <Text style={styles.tradeTime}>{formatTimestamp(item.created_at)}</Text>
          </View>
        </View>

        {/* right: P&L */}
        <View style={styles.tradeRight}>
          {item.pnl != null ? (
            <>
              <Text style={[styles.tradePnl, { color: pnlColor(item.pnl) }]}>
                {formatPnl(item.pnl, currency)}
              </Text>
              {item.pnl_pct != null && <PctBadge value={item.pnl_pct} />}
            </>
          ) : (
            <Text style={styles.tradePnlPending}>--</Text>
          )}
        </View>
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
        data={trades}
        keyExtractor={(item, index) => `${item.symbol}-${item.created_at}-${index}`}
        renderItem={renderTrade}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No trades yet</Text>
          </View>
        }
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.sky600} />
        }
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
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

  /* trade row */
  tradeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    backgroundColor: colors.white,
    borderRadius: 14,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.gray100,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  tradeLeft: {
    flex: 1,
    marginRight: 12,
  },
  tradeTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 6,
  },
  sideBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  sideText: {
    fontSize: 10,
    fontWeight: '800',
  },
  tradeSymbol: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.gray900,
  },
  tradeQtyPrice: {
    fontSize: 13,
    color: colors.gray500,
    marginBottom: 4,
  },
  tradeMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tradeStrategy: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.violet700,
    backgroundColor: colors.violet100,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 4,
    overflow: 'hidden',
    maxWidth: 140,
  },
  tradeTime: {
    fontSize: 11,
    color: colors.gray400,
  },
  tradeRight: {
    alignItems: 'flex-end',
    gap: 4,
  },
  tradePnl: {
    fontSize: 15,
    fontWeight: '700',
  },
  tradePnlPending: {
    fontSize: 14,
    color: colors.gray400,
    fontWeight: '500',
  },
  separator: {
    height: 8,
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
