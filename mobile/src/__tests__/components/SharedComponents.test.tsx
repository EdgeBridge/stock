import React from 'react'
import { render } from '@testing-library/react-native'
import {
  MarketPill,
  MktTag,
  PctBadge,
  PnlText,
  StatCard,
  InfoRow,
  SectionCard,
} from '../../components/SharedComponents'

describe('MarketPill', () => {
  it('renders "Open" for regular phase', () => {
    const { getByText } = render(<MarketPill label="US" phase="regular" />)
    expect(getByText('US Open')).toBeTruthy()
  })

  it('renders "Pre" for pre_market phase', () => {
    const { getByText } = render(<MarketPill label="KR" phase="pre_market" />)
    expect(getByText('KR Pre')).toBeTruthy()
  })

  it('renders "After" for after_hours phase', () => {
    const { getByText } = render(<MarketPill label="US" phase="after_hours" />)
    expect(getByText('US After')).toBeTruthy()
  })

  it('renders "Closed" for closed/unknown phase', () => {
    const { getByText } = render(<MarketPill label="KR" phase="closed" />)
    expect(getByText('KR Closed')).toBeTruthy()
  })
})

describe('MktTag', () => {
  it('renders market text', () => {
    const { getByText } = render(<MktTag mkt="US" />)
    expect(getByText('US')).toBeTruthy()
  })

  it('renders KR tag', () => {
    const { getByText } = render(<MktTag mkt="KR" />)
    expect(getByText('KR')).toBeTruthy()
  })
})

describe('PctBadge', () => {
  it('shows positive percentage with + sign', () => {
    const { getByText } = render(<PctBadge value={5.5} />)
    expect(getByText('+5.50%')).toBeTruthy()
  })

  it('shows negative percentage', () => {
    const { getByText } = render(<PctBadge value={-3.2} />)
    expect(getByText('-3.20%')).toBeTruthy()
  })

  it('shows zero with + sign', () => {
    const { getByText } = render(<PctBadge value={0} />)
    expect(getByText('+0.00%')).toBeTruthy()
  })
})

describe('PnlText', () => {
  it('renders positive P&L with + sign', () => {
    const { getByText } = render(<PnlText value={1234.56} currency="USD" />)
    const text = getByText(/\+/)
    expect(text).toBeTruthy()
  })

  it('renders negative P&L with - sign', () => {
    const { getByText } = render(<PnlText value={-500} currency="KRW" />)
    const text = getByText(/-/)
    expect(text).toBeTruthy()
  })
})

describe('StatCard', () => {
  it('renders label and value', () => {
    const { getByText } = render(<StatCard label="Cash" value="$10,000" />)
    expect(getByText('Cash')).toBeTruthy()
    expect(getByText('$10,000')).toBeTruthy()
  })
})

describe('InfoRow', () => {
  it('renders label and value', () => {
    const { getByText } = render(<InfoRow label="VIX" value="18.5" />)
    expect(getByText('VIX')).toBeTruthy()
    expect(getByText('18.5')).toBeTruthy()
  })
})

describe('SectionCard', () => {
  it('renders title when provided', () => {
    const { getByText } = render(
      <SectionCard title="Market">
        <InfoRow label="SPY" value="$500" />
      </SectionCard>
    )
    expect(getByText('Market')).toBeTruthy()
  })

  it('renders children', () => {
    const { getByText } = render(
      <SectionCard>
        <InfoRow label="Test" value="Value" />
      </SectionCard>
    )
    expect(getByText('Test')).toBeTruthy()
  })
})
