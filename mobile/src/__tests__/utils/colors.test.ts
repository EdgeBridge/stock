import { colors, pnlColor, pnlBg, phaseColor, phaseBg } from '../../utils/colors'

describe('colors', () => {
  it('exports all required colors', () => {
    expect(colors.emerald600).toBe('#059669')
    expect(colors.rose600).toBe('#E11D48')
    expect(colors.gray900).toBe('#111827')
    expect(colors.white).toBe('#FFFFFF')
  })
})

describe('pnlColor', () => {
  it('returns emerald for positive', () => {
    expect(pnlColor(100)).toBe(colors.emerald600)
  })

  it('returns rose for negative', () => {
    expect(pnlColor(-50)).toBe(colors.rose600)
  })

  it('returns emerald for zero', () => {
    expect(pnlColor(0)).toBe(colors.emerald600)
  })
})

describe('pnlBg', () => {
  it('returns emerald50 for positive', () => {
    expect(pnlBg(10)).toBe(colors.emerald50)
  })

  it('returns rose50 for negative', () => {
    expect(pnlBg(-10)).toBe(colors.rose50)
  })
})

describe('phaseColor', () => {
  it('returns correct color per phase', () => {
    expect(phaseColor('regular')).toBe(colors.emerald600)
    expect(phaseColor('pre_market')).toBe(colors.sky600)
    expect(phaseColor('after_hours')).toBe(colors.amber600)
    expect(phaseColor('closed')).toBe(colors.gray400)
    expect(phaseColor('anything')).toBe(colors.gray400)
  })
})

describe('phaseBg', () => {
  it('returns correct bg per phase', () => {
    expect(phaseBg('regular')).toBe(colors.emerald50)
    expect(phaseBg('pre_market')).toBe(colors.sky100)
    expect(phaseBg('after_hours')).toBe(colors.amber50)
    expect(phaseBg('closed')).toBe(colors.gray100)
  })
})
