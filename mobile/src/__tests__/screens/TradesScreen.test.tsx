import React from 'react'
import { render, waitFor, fireEvent } from '@testing-library/react-native'
import TradesScreen from '../../screens/TradesScreen'
import * as api from '../../api/client'

jest.mock('../../api/client')
const mockedApi = api as jest.Mocked<typeof api>

const mockTrades = [
  {
    symbol: 'AAPL',
    side: 'BUY',
    quantity: 10,
    price: 150,
    filled_price: 150.05,
    strategy: 'trend_following',
    status: 'filled',
    pnl: null,
    pnl_pct: null,
    created_at: '2026-04-16T09:30:00',
    market: 'US',
  },
  {
    symbol: 'MSFT',
    side: 'SELL',
    quantity: 5,
    price: 420,
    filled_price: 419.90,
    strategy: 'macd_histogram',
    status: 'filled',
    pnl: 125.50,
    pnl_pct: 3.2,
    created_at: '2026-04-16T14:00:00',
    market: 'US',
  },
]

describe('TradesScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedApi.fetchTrades.mockResolvedValue(mockTrades as any)
  })

  it('fetches trades on mount', async () => {
    render(<TradesScreen />)
    await waitFor(() => {
      expect(mockedApi.fetchTrades).toHaveBeenCalled()
    })
  })

  it('renders trade symbols', async () => {
    const { findByText } = render(<TradesScreen />)
    expect(await findByText('AAPL')).toBeTruthy()
    expect(await findByText('MSFT')).toBeTruthy()
  })

  it('renders BUY and SELL badges', async () => {
    const { findByText } = render(<TradesScreen />)
    expect(await findByText('BUY')).toBeTruthy()
    expect(await findByText('SELL')).toBeTruthy()
  })

  it('renders strategy names', async () => {
    const { findByText } = render(<TradesScreen />)
    expect(await findByText('trend_following')).toBeTruthy()
    expect(await findByText('macd_histogram')).toBeTruthy()
  })

  it('renders filter chips', async () => {
    const { findByText, findAllByText } = render(<TradesScreen />)
    expect(await findByText('All')).toBeTruthy()
    // 'US' appears in filter chip AND trade MktTags, so use findAllByText
    const usElements = await findAllByText('US')
    expect(usElements.length).toBeGreaterThanOrEqual(1)
    expect(await findByText('KR')).toBeTruthy()
  })

  it('shows empty state when no trades', async () => {
    mockedApi.fetchTrades.mockResolvedValue([])
    const { findByText } = render(<TradesScreen />)
    expect(await findByText(/no trades/i)).toBeTruthy()
  })
})
