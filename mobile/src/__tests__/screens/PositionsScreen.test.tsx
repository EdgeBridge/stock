import React from 'react'
import { render, waitFor, fireEvent } from '@testing-library/react-native'
import PositionsScreen from '../../screens/PositionsScreen'
import * as api from '../../api/client'

jest.mock('../../api/client')
const mockedApi = api as jest.Mocked<typeof api>

const mockPositions = [
  {
    symbol: 'NVDA',
    name: 'NVIDIA Corp',
    exchange: 'NASDAQ',
    quantity: 5,
    avg_price: 800,
    current_price: 950,
    unrealized_pnl: 750,
    unrealized_pnl_pct: 18.75,
    market: 'US',
    stop_loss_pct: 0.10,
    take_profit_pct: 0.20,
  },
  {
    symbol: '005930',
    name: 'Samsung',
    exchange: 'KRX',
    quantity: 100,
    avg_price: 70000,
    current_price: 72000,
    unrealized_pnl: 200000,
    unrealized_pnl_pct: 2.86,
    market: 'KR',
  },
]

describe('PositionsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedApi.fetchPositions.mockResolvedValue(mockPositions as any)
  })

  it('fetches positions on mount', async () => {
    render(<PositionsScreen />)
    await waitFor(() => {
      expect(mockedApi.fetchPositions).toHaveBeenCalledWith(undefined)
    })
  })

  it('renders position symbols', async () => {
    const { findByText } = render(<PositionsScreen />)
    expect(await findByText('NVDA')).toBeTruthy()
    expect(await findByText('005930')).toBeTruthy()
  })

  it('renders filter chips', async () => {
    const { findByText, findAllByText } = render(<PositionsScreen />)
    expect(await findByText('ALL')).toBeTruthy()
    // 'US' and 'KR' also appear in position MktTags, so use findAllByText
    const usElements = await findAllByText('US')
    expect(usElements.length).toBeGreaterThanOrEqual(1)
    const krElements = await findAllByText('KR')
    expect(krElements.length).toBeGreaterThanOrEqual(1)
  })

  it('re-fetches when filter changes', async () => {
    const { findByText, findAllByText } = render(<PositionsScreen />)
    await waitFor(() => expect(mockedApi.fetchPositions).toHaveBeenCalled())

    // Find the US filter chip (may have multiple 'US' texts due to MktTag)
    const usElements = await findAllByText('US')
    fireEvent.press(usElements[0])
    await waitFor(() => {
      expect(mockedApi.fetchPositions).toHaveBeenCalledWith('US')
    })
  })

  it('shows empty state when no positions', async () => {
    mockedApi.fetchPositions.mockResolvedValue([])
    const { findByText } = render(<PositionsScreen />)
    expect(await findByText(/no open positions/i)).toBeTruthy()
  })
})
