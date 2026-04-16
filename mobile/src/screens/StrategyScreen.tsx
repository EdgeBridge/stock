import React, { useState, useEffect, useCallback } from 'react'
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { colors } from '../utils/colors'
import { fetchStrategies, reloadStrategies } from '../api/client'
import type { Strategy } from '../types'

export default function StrategyScreen() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [expandedName, setExpandedName] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [reloading, setReloading] = useState(false)

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true)
    try {
      const data = await fetchStrategies()
      setStrategies(data)
    } catch {
      // silently ignore
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load(true)
  }, [load])

  const onRefresh = useCallback(() => {
    setRefreshing(true)
    load(false)
  }, [load])

  const handleReload = useCallback(async () => {
    setReloading(true)
    try {
      await reloadStrategies()
      await load(false)
      Alert.alert('Strategies', 'Configuration reloaded successfully.')
    } catch (err: any) {
      Alert.alert('Error', err?.message ?? 'Failed to reload strategies')
    } finally {
      setReloading(false)
    }
  }, [load])

  const toggleExpand = (name: string) => {
    setExpandedName((prev) => (prev === name ? null : name))
  }

  /* ── format param value ── */
  const formatValue = (val: unknown): string => {
    if (val === null || val === undefined) return '--'
    if (typeof val === 'boolean') return val ? 'Yes' : 'No'
    if (typeof val === 'number') return val.toLocaleString('en-US')
    if (Array.isArray(val)) return val.join(', ')
    if (typeof val === 'object') return JSON.stringify(val)
    return String(val)
  }

  /* ── timeframe badge color ── */
  const timeframeBg = (tf: string) => {
    if (tf === '1d') return colors.emerald50
    if (tf === '1h' || tf === '4h') return colors.sky100
    return colors.amber50
  }
  const timeframeFg = (tf: string) => {
    if (tf === '1d') return colors.emerald600
    if (tf === '1h' || tf === '4h') return colors.sky600
    return colors.amber600
  }

  const renderStrategy = ({ item }: { item: Strategy }) => {
    const isExpanded = expandedName === item.name
    const paramEntries = Object.entries(item.params ?? {})

    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => toggleExpand(item.name)}
        activeOpacity={0.7}
      >
        {/* header */}
        <View style={styles.cardHeader}>
          <View style={styles.cardLeft}>
            <Text style={styles.displayName}>{item.display_name}</Text>
            <Text style={styles.stratName}>{item.name}</Text>
          </View>
          <View style={styles.cardRight}>
            <View
              style={[
                styles.timeframeBadge,
                { backgroundColor: timeframeBg(item.timeframe) },
              ]}
            >
              <Text
                style={[
                  styles.timeframeText,
                  { color: timeframeFg(item.timeframe) },
                ]}
              >
                {item.timeframe}
              </Text>
            </View>
            <Ionicons
              name={isExpanded ? 'chevron-up' : 'chevron-down'}
              size={18}
              color={colors.gray400}
            />
          </View>
        </View>

        {/* expandable params */}
        {isExpanded && paramEntries.length > 0 && (
          <View style={styles.paramsContainer}>
            {paramEntries.map(([key, val]) => (
              <View key={key} style={styles.paramRow}>
                <Text style={styles.paramKey}>{key}</Text>
                <Text style={styles.paramVal} numberOfLines={2}>
                  {formatValue(val)}
                </Text>
              </View>
            ))}
          </View>
        )}

        {isExpanded && paramEntries.length === 0 && (
          <View style={styles.paramsContainer}>
            <Text style={styles.noParams}>No parameters</Text>
          </View>
        )}
      </TouchableOpacity>
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
      <FlatList
        data={strategies}
        keyExtractor={(item) => item.name}
        renderItem={renderStrategy}
        ListHeaderComponent={
          <Text style={styles.headerCount}>
            {strategies.length} strateg{strategies.length !== 1 ? 'ies' : 'y'}
          </Text>
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No strategies loaded</Text>
          </View>
        }
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.sky600}
          />
        }
        showsVerticalScrollIndicator={false}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
      />

      {/* FAB reload button */}
      <TouchableOpacity
        style={styles.fab}
        onPress={handleReload}
        disabled={reloading}
        activeOpacity={0.8}
      >
        {reloading ? (
          <ActivityIndicator size="small" color={colors.white} />
        ) : (
          <Ionicons name="reload" size={22} color={colors.white} />
        )}
      </TouchableOpacity>
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
    paddingBottom: 80,
  },
  headerCount: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.gray400,
    marginBottom: 10,
  },
  separator: {
    height: 8,
  },

  /* strategy card */
  card: {
    backgroundColor: colors.white,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.gray100,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
  },
  cardLeft: {
    flex: 1,
    marginRight: 12,
  },
  displayName: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.gray900,
  },
  stratName: {
    fontSize: 11,
    color: colors.gray400,
    marginTop: 2,
  },
  cardRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  timeframeBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  timeframeText: {
    fontSize: 11,
    fontWeight: '700',
  },

  /* params */
  paramsContainer: {
    borderTopWidth: 1,
    borderTopColor: colors.gray100,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: colors.gray50,
  },
  paramRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: 5,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.gray200,
  },
  paramKey: {
    fontSize: 12,
    color: colors.gray500,
    flex: 1,
    marginRight: 8,
  },
  paramVal: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.gray900,
    flex: 1,
    textAlign: 'right',
  },
  noParams: {
    fontSize: 13,
    color: colors.gray400,
    textAlign: 'center',
    paddingVertical: 4,
  },

  /* FAB */
  fab: {
    position: 'absolute',
    bottom: 24,
    right: 20,
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.sky600,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 6,
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
