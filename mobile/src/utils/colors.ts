export const colors = {
  emerald600: '#059669',
  emerald50: '#ECFDF5',
  rose600: '#E11D48',
  rose50: '#FFF1F2',
  sky600: '#0284C7',
  sky100: '#E0F2FE',
  violet700: '#6D28D9',
  violet100: '#EDE9FE',
  amber600: '#D97706',
  amber50: '#FFFBEB',
  gray50: '#F9FAFB',
  gray100: '#F3F4F6',
  gray200: '#E5E7EB',
  gray400: '#9CA3AF',
  gray500: '#6B7280',
  gray700: '#374151',
  gray900: '#111827',
  white: '#FFFFFF',
} as const

export function pnlColor(value: number) {
  return value >= 0 ? colors.emerald600 : colors.rose600
}

export function pnlBg(value: number) {
  return value >= 0 ? colors.emerald50 : colors.rose50
}

export function phaseColor(phase: string) {
  if (phase === 'regular') return colors.emerald600
  if (phase === 'pre_market') return colors.sky600
  if (phase === 'after_hours') return colors.amber600
  return colors.gray400
}

export function phaseBg(phase: string) {
  if (phase === 'regular') return colors.emerald50
  if (phase === 'pre_market') return colors.sky100
  if (phase === 'after_hours') return colors.amber50
  return colors.gray100
}
