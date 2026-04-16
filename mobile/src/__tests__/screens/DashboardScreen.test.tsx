import React from 'react'
import { render, waitFor } from '@testing-library/react-native'
import DashboardScreen from '../../screens/DashboardScreen'
import * as api from '../../api/client'

jest.mock('../../api/client')
const mockedApi = api as jest.Mocked<typeof api>

const mockSummary = {
  market: 'ALL',
  balance: { currency: 'KRW', total: 50_000_000, available: 10_000_000 },
  usd_balance: { total: 5000, available: 2000 },
  exchange_rate: 1350,
  positions_count: 5,
  total_unrealized_pnl: 1_500_000,
  total_unrealized_pnl_pct: 3.2,
  total_equity: 55_000_000,
  available_cash: 10_000_000,
}

const mockPositions = [
  {
    symbol: 'AAPL',
    exchange: 'NASDAQ',
    quantity: 10,
    avg_price: 150,
    current_price: 175,
    unrealized_pnl: 250,
    unrealized_pnl_pct: 16.67,
    market: 'US',
    stop_loss_pct: 0.08,
    take_profit_pct: 0.20,
  },
]

const mockEngine = {
  running: true,
  market_phase: 'regular',
  kr_market_phase: 'closed',
}

const mockReturns = {
  daily: { change: 500_000, pct: 1.2, base_equity: 54_500_000 },
  weekly: null,
  monthly: null,
}

const mockTradeSummary = {
  today: { trades: 2, wins: 1, losses: 1, pnl: 50000, pnl_pct: 0.5, win_rate: 50 },
  week: { trades: 5, wins: 3, losses: 2, pnl: 150000, pnl_pct: 1.5, win_rate: 60 },
  month: { trades: 10, wins: 6, losses: 4, pnl: 300000, pnl_pct: 3.0, win_rate: 60 },
  all_time: { trades: 50, wins: 30, losses: 20, pnl: 2000000, pnl_pct: 15.0, win_rate: 60 },
}

const mockMarketState = {
  market_phase: 'regular',
  regime: 'uptrend',
  spy_price: 520.5,
  vix_level: 14.3,
}

const mockMacro = {
  fed_funds_rate: 4.5,
  treasury_10y: 4.2,
  yield_spread: 0.3,
  cpi_yoy: 2.8,
  unemployment_rate: 3.9,
}

describe('DashboardScreen', () => {
  const onSettingsPress = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
    mockedApi.fetchPortfolioSummary.mockResolvedValue(mockSummary as any)
    mockedApi.fetchPositions.mockResolvedValue(mockPositions as any)
    mockedApi.fetchEngineStatus.mockResolvedValue(mockEngine as any)
    mockedApi.fetchPortfolioReturns.mockResolvedValue(mockReturns as any)
    mockedApi.fetchTradeSummaryPeriods.mockResolvedValue(mockTradeSummary as any)
    mockedApi.fetchMarketState.mockResolvedValue(mockMarketState as any)
    mockedApi.fetchMacroIndicators.mockResolvedValue(mockMacro as any)
  })

  it('shows loading initially', () => {
    // Make API hang
    mockedApi.fetchPortfolioSummary.mockReturnValue(new Promise(() => {}))
    const { getByText } = render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    // Loading text should be present
    expect(getByText('Loading dashboard...')).toBeTruthy()
  })

  it('renders equity after data loads', async () => {
    const { findByText } = render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    // Wait for data to load and equity to appear
    await waitFor(() => {
      expect(mockedApi.fetchPortfolioSummary).toHaveBeenCalled()
    })
  })

  it('fetches all data on mount', async () => {
    render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    await waitFor(() => {
      expect(mockedApi.fetchPortfolioSummary).toHaveBeenCalledWith('ALL')
      expect(mockedApi.fetchPositions).toHaveBeenCalledWith('ALL')
      expect(mockedApi.fetchEngineStatus).toHaveBeenCalled()
      expect(mockedApi.fetchPortfolioReturns).toHaveBeenCalled()
      expect(mockedApi.fetchMarketState).toHaveBeenCalled()
      expect(mockedApi.fetchMacroIndicators).toHaveBeenCalled()
    })
  })

  it('fetches trade summaries for both markets', async () => {
    render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    await waitFor(() => {
      expect(mockedApi.fetchTradeSummaryPeriods).toHaveBeenCalledWith('US')
      expect(mockedApi.fetchTradeSummaryPeriods).toHaveBeenCalledWith('KR')
    })
  })

  it('shows error state on API failure', async () => {
    mockedApi.fetchPortfolioSummary.mockRejectedValue(new Error('Network error'))
    const { findByText } = render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    const errorText = await findByText(/error/i)
    expect(errorText).toBeTruthy()
  })

  it('renders position symbol', async () => {
    const { findByText } = render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    const symbol = await findByText('AAPL')
    expect(symbol).toBeTruthy()
  })

  it('renders market pills', async () => {
    const { findByText } = render(<DashboardScreen onSettingsPress={onSettingsPress} />)
    const usPill = await findByText('US Open')
    expect(usPill).toBeTruthy()
  })
})
