import { formatCurrency, formatPnl, formatPct, formatTimestamp } from '../../utils/format'

describe('formatCurrency', () => {
  it('formats KRW without decimals', () => {
    const result = formatCurrency(1234567, 'KRW')
    expect(result).toMatch(/1,234,567/)
    expect(result).toContain('원')
  })

  it('formats USD with 2 decimals', () => {
    const result = formatCurrency(1234.5, 'USD')
    expect(result).toContain('$')
    expect(result).toMatch(/1,234\.50/)
  })

  it('formats zero', () => {
    expect(formatCurrency(0, 'KRW')).toContain('0')
    expect(formatCurrency(0, 'USD')).toContain('$')
  })

  it('uses absolute value', () => {
    const result = formatCurrency(-500, 'KRW')
    expect(result).toMatch(/500/)
    expect(result).not.toContain('-')
  })
})

describe('formatPnl', () => {
  it('adds + sign for positive values', () => {
    const result = formatPnl(100, 'USD')
    expect(result).toMatch(/^\+/)
  })

  it('adds - sign for negative values', () => {
    const result = formatPnl(-100, 'USD')
    expect(result).toMatch(/^-/)
  })

  it('adds + for zero', () => {
    const result = formatPnl(0, 'KRW')
    expect(result).toMatch(/^\+/)
  })
})

describe('formatPct', () => {
  it('formats positive with + sign', () => {
    expect(formatPct(5.123)).toBe('+5.12%')
  })

  it('formats negative with - sign', () => {
    expect(formatPct(-3.456)).toBe('-3.46%')
  })

  it('formats zero', () => {
    expect(formatPct(0)).toBe('+0.00%')
  })
})

describe('formatTimestamp', () => {
  it('formats ISO timestamp to short form', () => {
    expect(formatTimestamp('2026-04-16T09:30:00')).toBe('04/16 09:30')
  })

  it('handles date-only input', () => {
    expect(formatTimestamp('2026-04-16')).toBe('04/16 ')
  })

  it('returns dash on empty input', () => {
    expect(formatTimestamp('')).toBe('--')
  })
})
