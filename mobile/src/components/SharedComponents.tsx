import React from 'react'
import { View, Text, StyleSheet } from 'react-native'
import { colors, pnlColor, pnlBg, phaseColor, phaseBg } from '../utils/colors'
import { formatCurrency, formatPnl, formatPct } from '../utils/format'

/* ─── MarketPill ─── */

const phaseLabel = (phase: string): string => {
  if (phase === 'regular') return 'Open'
  if (phase === 'pre_market') return 'Pre'
  if (phase === 'after_hours') return 'After'
  return 'Closed'
}

interface MarketPillProps {
  label: string
  phase: string
}

export function MarketPill({ label, phase }: MarketPillProps) {
  const bg = phaseBg(phase)
  const fg = phaseColor(phase)
  const isOpen = phase === 'regular'

  return (
    <View style={[pillStyles.container, { backgroundColor: bg }]}>
      <View style={[pillStyles.dot, { backgroundColor: fg, opacity: isOpen ? 1 : 0.7 }]} />
      <Text style={[pillStyles.text, { color: fg }]}>
        {label} {phaseLabel(phase)}
      </Text>
    </View>
  )
}

const pillStyles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  text: {
    fontSize: 11,
    fontWeight: '700',
  },
})

/* ─── MktTag ─── */

interface MktTagProps {
  mkt: string
}

export function MktTag({ mkt }: MktTagProps) {
  const isKR = mkt === 'KR'
  return (
    <View
      style={[
        tagStyles.container,
        { backgroundColor: isKR ? colors.violet100 : colors.sky100 },
      ]}
    >
      <Text
        style={[
          tagStyles.text,
          { color: isKR ? colors.violet700 : colors.sky600 },
        ]}
      >
        {mkt}
      </Text>
    </View>
  )
}

const tagStyles = StyleSheet.create({
  container: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 999,
  },
  text: {
    fontSize: 10,
    fontWeight: '700',
  },
})

/* ─── PctBadge ─── */

interface PctBadgeProps {
  value: number
}

export function PctBadge({ value }: PctBadgeProps) {
  const bg = pnlBg(value)
  const fg = pnlColor(value)

  return (
    <View style={[badgeStyles.container, { backgroundColor: bg }]}>
      <Text style={[badgeStyles.text, { color: fg }]}>
        {formatPct(value)}
      </Text>
    </View>
  )
}

const badgeStyles = StyleSheet.create({
  container: {
    alignSelf: 'flex-start',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  text: {
    fontSize: 11,
    fontWeight: '700',
  },
})

/* ─── PnlText ─── */

interface PnlTextProps {
  value: number
  currency: string
}

export function PnlText({ value, currency }: PnlTextProps) {
  const fg = pnlColor(value)

  return (
    <Text style={[pnlStyles.text, { color: fg }]}>
      {formatPnl(value, currency)}
    </Text>
  )
}

const pnlStyles = StyleSheet.create({
  text: {
    fontSize: 14,
    fontWeight: '600',
  },
})

/* ─── StatCard ─── */

interface StatCardProps {
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
}

export function StatCard({ label, value, sub }: StatCardProps) {
  return (
    <View style={statStyles.card}>
      <Text style={statStyles.label}>{label}</Text>
      {typeof value === 'string' ? (
        <Text style={statStyles.value} numberOfLines={1}>
          {value}
        </Text>
      ) : (
        <View style={statStyles.valueWrap}>{value}</View>
      )}
      {sub != null && <View style={statStyles.subWrap}>{sub}</View>}
    </View>
  )
}

const statStyles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: colors.white,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.gray100,
    paddingHorizontal: 12,
    paddingVertical: 10,
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
  },
  value: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.gray900,
    marginTop: 2,
  },
  valueWrap: {
    marginTop: 2,
  },
  subWrap: {
    marginTop: 2,
  },
})

/* ─── InfoRow ─── */

interface InfoRowProps {
  label: string
  value: string
  color?: string
}

export function InfoRow({ label, value, color }: InfoRowProps) {
  return (
    <View style={infoStyles.row}>
      <Text style={infoStyles.label}>{label}</Text>
      <Text style={[infoStyles.value, color ? { color } : undefined]}>
        {value}
      </Text>
    </View>
  )
}

const infoStyles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    paddingVertical: 2,
  },
  label: {
    fontSize: 12,
    color: colors.gray400,
  },
  value: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.gray900,
  },
})

/* ─── SectionCard ─── */

interface SectionCardProps {
  title?: string
  children: React.ReactNode
}

export function SectionCard({ title, children }: SectionCardProps) {
  return (
    <View style={sectionStyles.card}>
      {title != null && (
        <View style={sectionStyles.header}>
          <Text style={sectionStyles.title}>{title}</Text>
        </View>
      )}
      <View style={title != null ? sectionStyles.body : sectionStyles.bodyNoHeader}>
        {children}
      </View>
    </View>
  )
}

const sectionStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.gray100,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  header: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.gray100,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.gray900,
  },
  body: {
    padding: 16,
  },
  bodyNoHeader: {
    padding: 16,
  },
})
