import React, { useState, useEffect, useCallback } from 'react'
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native'
import { colors } from '../utils/colors'
import { SectionCard, InfoRow } from '../components/SharedComponents'
import {
  fetchEngineStatus,
  startEngine,
  stopEngine,
  runEvaluation,
  fetchETFStatus,
} from '../api/client'
import type { EngineStatus, ETFStatus, TaskInfo } from '../types'

export default function EngineScreen() {
  const [engine, setEngine] = useState<EngineStatus | null>(null)
  const [etf, setEtf] = useState<ETFStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true)
    try {
      const [engineData, etfData] = await Promise.all([
        fetchEngineStatus(),
        fetchETFStatus().catch(() => null),
      ])
      setEngine(engineData)
      setEtf(etfData)
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

  /* ── actions ── */
  const handleStartStop = useCallback(async () => {
    if (!engine) return
    const action = engine.running ? 'Stop' : 'Start'

    Alert.alert(
      `${action} Engine`,
      `Are you sure you want to ${action.toLowerCase()} the trading engine?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: action,
          style: engine.running ? 'destructive' : 'default',
          onPress: async () => {
            setActionLoading(action.toLowerCase())
            try {
              if (engine.running) {
                await stopEngine()
              } else {
                await startEngine()
              }
              await load(false)
            } catch (err: any) {
              Alert.alert('Error', err?.message ?? `Failed to ${action.toLowerCase()} engine`)
            } finally {
              setActionLoading(null)
            }
          },
        },
      ],
    )
  }, [engine, load])

  const handleEvaluate = useCallback(async () => {
    setActionLoading('evaluate')
    try {
      await runEvaluation()
      Alert.alert('Evaluation', 'Evaluation cycle completed successfully.')
      await load(false)
    } catch (err: any) {
      Alert.alert('Error', err?.message ?? 'Evaluation failed')
    } finally {
      setActionLoading(null)
    }
  }, [load])

  /* ── render helpers ── */

  const renderEngineCard = () => {
    if (!engine) return null
    const running = engine.running
    return (
      <SectionCard title="Engine Status">
        <View style={styles.statusRow}>
          <View style={styles.statusIndicator}>
            <View
              style={[
                styles.statusDot,
                { backgroundColor: running ? colors.emerald600 : colors.rose600 },
              ]}
            />
            <Text
              style={[
                styles.statusText,
                { color: running ? colors.emerald600 : colors.rose600 },
              ]}
            >
              {running ? 'Running' : 'Stopped'}
            </Text>
          </View>
        </View>

        <View style={styles.phaseRow}>
          <InfoRow label="US Phase" value={engine.market_phase ?? 'N/A'} />
          {engine.kr_market_phase != null && (
            <InfoRow label="KR Phase" value={engine.kr_market_phase} />
          )}
        </View>

        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[
              styles.actionBtn,
              running ? styles.stopBtn : styles.startBtn,
            ]}
            onPress={handleStartStop}
            disabled={actionLoading != null}
            activeOpacity={0.7}
          >
            {actionLoading === 'start' || actionLoading === 'stop' ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <Text style={styles.actionBtnText}>
                {running ? 'Stop' : 'Start'}
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, styles.evaluateBtn]}
            onPress={handleEvaluate}
            disabled={actionLoading != null}
            activeOpacity={0.7}
          >
            {actionLoading === 'evaluate' ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <Text style={styles.actionBtnText}>Evaluate</Text>
            )}
          </TouchableOpacity>
        </View>
      </SectionCard>
    )
  }

  const renderETFCard = () => {
    if (!etf) return null
    const managed = etf.managed_positions ?? {}
    const managedEntries = Object.entries(managed)

    return (
      <SectionCard title="ETF Engine">
        <InfoRow label="Status" value={etf.status ?? 'N/A'} />
        <InfoRow label="Regime" value={etf.last_regime ?? 'N/A'} />
        {etf.top_sectors.length > 0 && (
          <InfoRow label="Top Sectors" value={etf.top_sectors.join(', ')} />
        )}

        {managedEntries.length > 0 && (
          <View style={styles.managedSection}>
            <Text style={styles.managedTitle}>Managed Positions</Text>
            {managedEntries.map(([symbol, pos]) => (
              <View key={symbol} style={styles.managedRow}>
                <Text style={styles.managedSymbol}>{symbol}</Text>
                <View style={styles.managedMeta}>
                  <Text style={styles.managedDetail}>{pos.sector}</Text>
                  <Text style={styles.managedDetail}>
                    {pos.hold_days}d hold
                  </Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </SectionCard>
    )
  }

  const renderTasksCard = () => {
    const tasks = engine?.tasks ?? []
    if (tasks.length === 0) return null

    return (
      <SectionCard title={`Tasks (${tasks.length})`}>
        <ScrollView
          style={styles.taskScroll}
          nestedScrollEnabled
          showsVerticalScrollIndicator={false}
        >
          {tasks.map((task) => (
            <View key={task.name} style={styles.taskRow}>
              <View style={styles.taskLeft}>
                <View
                  style={[
                    styles.taskDot,
                    {
                      backgroundColor: task.active
                        ? colors.emerald600
                        : colors.gray400,
                    },
                  ]}
                />
                <Text style={styles.taskName} numberOfLines={1}>
                  {task.name}
                </Text>
              </View>
              <Text style={styles.taskInterval}>
                {task.interval_sec >= 3600
                  ? `${(task.interval_sec / 3600).toFixed(1)}h`
                  : `${Math.round(task.interval_sec / 60)}m`}
              </Text>
            </View>
          ))}
        </ScrollView>
      </SectionCard>
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
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.sky600} />
      }
      showsVerticalScrollIndicator={false}
    >
      {renderEngineCard()}
      {renderETFCard()}
      {renderTasksCard()}
    </ScrollView>
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
  content: {
    padding: 16,
    paddingBottom: 32,
    gap: 14,
  },

  /* engine status */
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  statusIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  statusText: {
    fontSize: 16,
    fontWeight: '800',
  },
  phaseRow: {
    marginBottom: 14,
    gap: 2,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
  },
  startBtn: {
    backgroundColor: colors.emerald600,
  },
  stopBtn: {
    backgroundColor: colors.rose600,
  },
  evaluateBtn: {
    backgroundColor: colors.sky600,
  },
  actionBtnText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '700',
  },

  /* ETF managed positions */
  managedSection: {
    marginTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.gray100,
    paddingTop: 10,
  },
  managedTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.gray400,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  managedRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.gray100,
  },
  managedSymbol: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.gray900,
  },
  managedMeta: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  managedDetail: {
    fontSize: 12,
    color: colors.gray500,
  },

  /* tasks */
  taskScroll: {
    maxHeight: 300,
  },
  taskRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.gray100,
  },
  taskLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    marginRight: 8,
  },
  taskDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  taskName: {
    fontSize: 13,
    fontWeight: '500',
    color: colors.gray700,
    flexShrink: 1,
  },
  taskInterval: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.gray400,
  },
})
