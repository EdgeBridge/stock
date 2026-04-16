import axios, { AxiosInstance } from 'axios'
import type {
  PortfolioSummary,
  Position,
  PortfolioReturns,
  TradeSummaryPeriods,
  EngineStatus,
  MarketState,
  MacroIndicators,
  Trade,
  Strategy,
  ETFStatus,
} from '../types'

let apiInstance: AxiosInstance | null = null

export function initApi(baseUrl: string, token?: string) {
  apiInstance = axios.create({
    baseURL: `${baseUrl.replace(/\/+$/, '')}/api/v1`,
    timeout: 15_000,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}

function api(): AxiosInstance {
  if (!apiInstance) throw new Error('API not initialized. Call initApi() first.')
  return apiInstance
}

// Portfolio
export const fetchPortfolioSummary = (market = 'ALL') =>
  api().get<PortfolioSummary>('/portfolio/summary', { params: { market } }).then(r => r.data)

export const fetchPositions = (market = 'ALL') =>
  api().get<Position[]>('/portfolio/positions', { params: { market } }).then(r => r.data)

export const fetchPortfolioReturns = () =>
  api().get<PortfolioReturns>('/portfolio/returns').then(r => r.data)

export const fetchTradeSummaryPeriods = (market?: string) =>
  api().get<TradeSummaryPeriods>('/portfolio/trade-summary', {
    params: market ? { market } : {},
  }).then(r => r.data)

// Engine
export const fetchEngineStatus = () =>
  api().get<EngineStatus>('/engine/status').then(r => r.data)

export const startEngine = () =>
  api().post<{ message?: string }>('/engine/start').then(r => r.data)

export const stopEngine = () =>
  api().post<{ message?: string }>('/engine/stop').then(r => r.data)

export const runEvaluation = () =>
  api().post<{ message?: string }>('/engine/evaluate', {}, { timeout: 120_000 }).then(r => r.data)

export const fetchMarketState = () =>
  api().get<MarketState>('/engine/market-state').then(r => r.data)

export const fetchMacroIndicators = () =>
  api().get<MacroIndicators>('/engine/macro').then(r => r.data)

export const fetchETFStatus = (market = 'US') =>
  api().get<ETFStatus>(market === 'KR' ? '/engine/etf/kr' : '/engine/etf').then(r => r.data)

// Trades
export const fetchTrades = (opts: { limit?: number; offset?: number; market?: string } = {}) => {
  const { limit = 50, offset = 0, market } = opts
  return api().get<Trade[]>('/trades/', {
    params: { limit, offset, ...(market && { market }) },
  }).then(r => r.data)
}

// Strategies
export const fetchStrategies = () =>
  api().get<Strategy[]>('/strategies/').then(r => r.data)

export const reloadStrategies = () =>
  api().post<{ message?: string }>('/strategies/reload').then(r => r.data)
