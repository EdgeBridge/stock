import axios from 'axios'
import type {
  PortfolioSummary,
  Position,
  TickerData,
  ChartData,
  Strategy,
  ScanResult,
  EngineStatus,
  WatchlistResponse,
  Trade,
  TradeSummary,
} from '../types'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
})

// Portfolio
export const fetchPortfolioSummary = () =>
  api.get<PortfolioSummary>('/portfolio/summary').then(r => r.data)

export const fetchPositions = () =>
  api.get<Position[]>('/portfolio/positions').then(r => r.data)

// Market
export const fetchPrice = (symbol: string) =>
  api.get<TickerData>(`/market/price/${symbol}`).then(r => r.data)

export const fetchChart = (symbol: string, timeframe = '1D', limit = 200) =>
  api.get<ChartData>(`/market/chart/${symbol}`, {
    params: { timeframe, limit },
  }).then(r => r.data)

// Strategies
export const fetchStrategies = () =>
  api.get<Strategy[]>('/strategies/').then(r => r.data)

export const reloadStrategies = () =>
  api.post('/strategies/reload').then(r => r.data)

// Scanner
export const runScan = (symbols: string[], minGrade = 'B', maxCandidates = 20) =>
  api.post<ScanResult[]>('/scanner/run', {
    symbols,
    min_grade: minGrade,
    max_candidates: maxCandidates,
  }).then(r => r.data)

export const fetchSectorPerformance = () =>
  api.get('/scanner/sectors').then(r => r.data)

// Engine
export const fetchEngineStatus = () =>
  api.get<EngineStatus>('/engine/status').then(r => r.data)

export const startEngine = () =>
  api.post('/engine/start').then(r => r.data)

export const stopEngine = () =>
  api.post('/engine/stop').then(r => r.data)

// Watchlist
export const fetchWatchlist = () =>
  api.get<WatchlistResponse>('/watchlist/').then(r => r.data)

export const addToWatchlist = (symbol: string) =>
  api.post<WatchlistResponse>('/watchlist/', { symbol }).then(r => r.data)

export const removeFromWatchlist = (symbol: string) =>
  api.delete<WatchlistResponse>(`/watchlist/${symbol}`).then(r => r.data)

// Trades
export const fetchTrades = (limit = 50) =>
  api.get<Trade[]>('/trades/', { params: { limit } }).then(r => r.data)

export const fetchTradeSummary = () =>
  api.get<TradeSummary>('/trades/summary').then(r => r.data)

// Backtest
export const runBacktest = (params: {
  strategy_name: string
  symbol: string
  period?: string
  initial_equity?: number
}) => api.post('/backtest/run', params).then(r => r.data)

export const fetchBacktestStrategies = () =>
  api.get('/backtest/strategies').then(r => r.data)

// Portfolio history
export const fetchEquityHistory = (days = 30) =>
  api.get('/portfolio/equity-history', { params: { days } }).then(r => r.data)

// Recovery
export const fetchRecoveryStatus = () =>
  api.get('/engine/recovery').then(r => r.data)
