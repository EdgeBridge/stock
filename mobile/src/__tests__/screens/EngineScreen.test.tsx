import React from 'react'
import { render, waitFor, fireEvent } from '@testing-library/react-native'
import EngineScreen from '../../screens/EngineScreen'
import * as api from '../../api/client'
import { Alert } from 'react-native'

jest.mock('../../api/client')
const mockedApi = api as jest.Mocked<typeof api>

const mockEngineRunning = {
  running: true,
  market_phase: 'regular',
  kr_market_phase: 'closed',
  tasks: [
    { name: 'evaluate_us', interval_sec: 300, phases: ['regular'], last_run: null, active: true },
    { name: 'portfolio_snapshot', interval_sec: 3600, phases: null, last_run: null, active: true },
  ],
}

const mockEngineOff = {
  running: false,
  market_phase: 'closed',
  tasks: [],
}

const mockEtf = {
  status: 'active',
  last_regime: 'uptrend',
  top_sectors: ['Technology', 'Healthcare'],
  managed_positions: {
    TQQQ: { reason: 'regime_bull', sector: '', hold_days: 3 },
  },
}

describe('EngineScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedApi.fetchEngineStatus.mockResolvedValue(mockEngineRunning as any)
    mockedApi.fetchETFStatus.mockResolvedValue(mockEtf as any)
    jest.spyOn(Alert, 'alert').mockImplementation(() => {})
  })

  it('fetches engine status on mount', async () => {
    render(<EngineScreen />)
    await waitFor(() => {
      expect(mockedApi.fetchEngineStatus).toHaveBeenCalled()
    })
  })

  it('shows Running when engine is on', async () => {
    const { findByText } = render(<EngineScreen />)
    expect(await findByText('Running')).toBeTruthy()
  })

  it('shows Stopped when engine is off', async () => {
    mockedApi.fetchEngineStatus.mockResolvedValue(mockEngineOff as any)
    mockedApi.fetchETFStatus.mockResolvedValue({ status: null, last_regime: null, top_sectors: [], managed_positions: {} } as any)
    const { findByText } = render(<EngineScreen />)
    expect(await findByText('Stopped')).toBeTruthy()
  })

  it('renders ETF engine info', async () => {
    const { findByText } = render(<EngineScreen />)
    expect(await findByText(/uptrend/i)).toBeTruthy()
    expect(await findByText('TQQQ')).toBeTruthy()
  })

  it('renders task list', async () => {
    const { findByText } = render(<EngineScreen />)
    expect(await findByText('evaluate_us')).toBeTruthy()
    expect(await findByText('portfolio_snapshot')).toBeTruthy()
  })
})
