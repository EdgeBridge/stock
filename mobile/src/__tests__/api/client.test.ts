import axios from 'axios'
import {
  initApi,
  fetchPortfolioSummary,
  fetchPositions,
  fetchPortfolioReturns,
  fetchTradeSummaryPeriods,
  fetchEngineStatus,
  startEngine,
  stopEngine,
  runEvaluation,
  fetchMarketState,
  fetchMacroIndicators,
  fetchETFStatus,
  fetchTrades,
  fetchStrategies,
  reloadStrategies,
} from '../../api/client'

// axios is already mocked via __mocks__/axios.ts + jest.setup.js
const mockedAxios = axios as jest.Mocked<typeof axios>

const mockInstance = {
  get: jest.fn(),
  post: jest.fn(),
}

beforeEach(() => {
  jest.clearAllMocks()
  mockedAxios.create.mockReturnValue(mockInstance as any)
  initApi('https://test.example.com', 'test-token')
})

describe('initApi', () => {
  it('creates axios instance with correct baseURL', () => {
    expect(mockedAxios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        baseURL: 'https://test.example.com/api/v1',
        timeout: 15000,
      })
    )
  })

  it('sets authorization header when token provided', () => {
    expect(mockedAxios.create).toHaveBeenCalledWith(
      expect.objectContaining({
        headers: { Authorization: 'Bearer test-token' },
      })
    )
  })

  it('strips trailing slashes from URL', () => {
    initApi('https://test.example.com///')
    expect(mockedAxios.create).toHaveBeenLastCalledWith(
      expect.objectContaining({
        baseURL: 'https://test.example.com/api/v1',
      })
    )
  })
})

describe('portfolio endpoints', () => {
  it('fetchPortfolioSummary calls correct endpoint', async () => {
    const mockData = { market: 'ALL', balance: { total: 1000 } }
    mockInstance.get.mockResolvedValue({ data: mockData })
    const result = await fetchPortfolioSummary('ALL')
    expect(mockInstance.get).toHaveBeenCalledWith('/portfolio/summary', { params: { market: 'ALL' } })
    expect(result).toEqual(mockData)
  })

  it('fetchPositions passes market param', async () => {
    mockInstance.get.mockResolvedValue({ data: [] })
    await fetchPositions('US')
    expect(mockInstance.get).toHaveBeenCalledWith('/portfolio/positions', { params: { market: 'US' } })
  })

  it('fetchPortfolioReturns calls correct endpoint', async () => {
    mockInstance.get.mockResolvedValue({ data: { daily: null } })
    await fetchPortfolioReturns()
    expect(mockInstance.get).toHaveBeenCalledWith('/portfolio/returns')
  })

  it('fetchTradeSummaryPeriods passes market when provided', async () => {
    mockInstance.get.mockResolvedValue({ data: {} })
    await fetchTradeSummaryPeriods('KR')
    expect(mockInstance.get).toHaveBeenCalledWith('/portfolio/trade-summary', { params: { market: 'KR' } })
  })

  it('fetchTradeSummaryPeriods passes empty params when no market', async () => {
    mockInstance.get.mockResolvedValue({ data: {} })
    await fetchTradeSummaryPeriods()
    expect(mockInstance.get).toHaveBeenCalledWith('/portfolio/trade-summary', { params: {} })
  })
})

describe('engine endpoints', () => {
  it('fetchEngineStatus calls correct endpoint', async () => {
    mockInstance.get.mockResolvedValue({ data: { running: true } })
    const result = await fetchEngineStatus()
    expect(mockInstance.get).toHaveBeenCalledWith('/engine/status')
    expect(result.running).toBe(true)
  })

  it('startEngine calls POST', async () => {
    mockInstance.post.mockResolvedValue({ data: { message: 'Started' } })
    const result = await startEngine()
    expect(mockInstance.post).toHaveBeenCalledWith('/engine/start')
    expect(result.message).toBe('Started')
  })

  it('stopEngine calls POST', async () => {
    mockInstance.post.mockResolvedValue({ data: { message: 'Stopped' } })
    await stopEngine()
    expect(mockInstance.post).toHaveBeenCalledWith('/engine/stop')
  })

  it('runEvaluation calls POST with timeout', async () => {
    mockInstance.post.mockResolvedValue({ data: {} })
    await runEvaluation()
    expect(mockInstance.post).toHaveBeenCalledWith('/engine/evaluate', {}, { timeout: 120000 })
  })

  it('fetchMarketState calls correct endpoint', async () => {
    mockInstance.get.mockResolvedValue({ data: { regime: 'uptrend' } })
    await fetchMarketState()
    expect(mockInstance.get).toHaveBeenCalledWith('/engine/market-state')
  })

  it('fetchMacroIndicators calls correct endpoint', async () => {
    mockInstance.get.mockResolvedValue({ data: {} })
    await fetchMacroIndicators()
    expect(mockInstance.get).toHaveBeenCalledWith('/engine/macro')
  })

  it('fetchETFStatus defaults to US', async () => {
    mockInstance.get.mockResolvedValue({ data: {} })
    await fetchETFStatus()
    expect(mockInstance.get).toHaveBeenCalledWith('/engine/etf')
  })

  it('fetchETFStatus routes KR to /engine/etf/kr', async () => {
    mockInstance.get.mockResolvedValue({ data: {} })
    await fetchETFStatus('KR')
    expect(mockInstance.get).toHaveBeenCalledWith('/engine/etf/kr')
  })
})

describe('trades endpoints', () => {
  it('fetchTrades with defaults', async () => {
    mockInstance.get.mockResolvedValue({ data: [] })
    await fetchTrades()
    expect(mockInstance.get).toHaveBeenCalledWith('/trades/', {
      params: { limit: 50, offset: 0 },
    })
  })

  it('fetchTrades with market filter', async () => {
    mockInstance.get.mockResolvedValue({ data: [] })
    await fetchTrades({ market: 'US', limit: 10 })
    expect(mockInstance.get).toHaveBeenCalledWith('/trades/', {
      params: { limit: 10, offset: 0, market: 'US' },
    })
  })
})

describe('strategy endpoints', () => {
  it('fetchStrategies calls correct endpoint', async () => {
    mockInstance.get.mockResolvedValue({ data: [] })
    await fetchStrategies()
    expect(mockInstance.get).toHaveBeenCalledWith('/strategies/')
  })

  it('reloadStrategies calls POST', async () => {
    mockInstance.post.mockResolvedValue({ data: { message: 'Reloaded' } })
    const result = await reloadStrategies()
    expect(mockInstance.post).toHaveBeenCalledWith('/strategies/reload')
    expect(result.message).toBe('Reloaded')
  })
})
