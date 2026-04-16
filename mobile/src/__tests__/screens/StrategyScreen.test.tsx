import React from 'react'
import { render, waitFor, fireEvent } from '@testing-library/react-native'
import StrategyScreen from '../../screens/StrategyScreen'
import * as api from '../../api/client'

jest.mock('../../api/client')
const mockedApi = api as jest.Mocked<typeof api>

const mockStrategies = [
  {
    name: 'trend_following',
    display_name: 'Trend Following',
    timeframe: '1D',
    params: { ema_fast: 20, ema_slow: 50, ema_long: 200 },
  },
  {
    name: 'macd_histogram',
    display_name: 'MACD Histogram',
    timeframe: '1D',
    params: { fast_period: 8, slow_period: 20, signal_period: 7 },
  },
]

describe('StrategyScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedApi.fetchStrategies.mockResolvedValue(mockStrategies as any)
    mockedApi.reloadStrategies.mockResolvedValue({ message: 'Reloaded' })
  })

  it('fetches strategies on mount', async () => {
    render(<StrategyScreen />)
    await waitFor(() => {
      expect(mockedApi.fetchStrategies).toHaveBeenCalled()
    })
  })

  it('renders strategy names', async () => {
    const { findByText } = render(<StrategyScreen />)
    expect(await findByText('Trend Following')).toBeTruthy()
    expect(await findByText('MACD Histogram')).toBeTruthy()
  })

  it('renders timeframe badges', async () => {
    const { findAllByText } = render(<StrategyScreen />)
    const badges = await findAllByText('1D')
    expect(badges.length).toBe(2)
  })

  it('expands params on tap', async () => {
    const { findByText, queryByText } = render(<StrategyScreen />)
    // Params should not be visible initially
    await findByText('Trend Following')

    // Tap to expand
    fireEvent.press(await findByText('Trend Following'))
    // After expansion, params should appear
    await waitFor(() => {
      expect(queryByText('ema_fast')).toBeTruthy()
    })
  })

  it('shows empty state when no strategies', async () => {
    mockedApi.fetchStrategies.mockResolvedValue([])
    const { findByText } = render(<StrategyScreen />)
    expect(await findByText(/no strategies/i)).toBeTruthy()
  })
})
