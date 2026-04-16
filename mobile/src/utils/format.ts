export function formatCurrency(value: number, currency: string): string {
  if (currency === 'USD') {
    return `$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
  return `${Math.abs(value).toLocaleString('ko-KR', { maximumFractionDigits: 0 })}원`
}

export function formatPnl(value: number, currency: string): string {
  const sign = value >= 0 ? '+' : '-'
  return `${sign}${formatCurrency(value, currency)}`
}

export function formatPct(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

export function formatTimestamp(ts: string): string {
  if (!ts) return '--'
  try {
    const [date, time] = ts.split('T')
    return `${date.substring(5).replace('-', '/')} ${(time ?? '').substring(0, 5)}`
  } catch {
    return ts
  }
}
