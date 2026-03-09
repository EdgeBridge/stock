import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/client'

export function usePortfolioSummary(market = 'US') {
  return useQuery({
    queryKey: ['portfolio', 'summary', market],
    queryFn: () => api.fetchPortfolioSummary(market),
  })
}

export function usePositions(market = 'US') {
  return useQuery({
    queryKey: ['portfolio', 'positions', market],
    queryFn: () => api.fetchPositions(market),
  })
}

export function usePrice(symbol: string) {
  return useQuery({
    queryKey: ['market', 'price', symbol],
    queryFn: () => api.fetchPrice(symbol),
    enabled: !!symbol,
  })
}

export function useChart(symbol: string, timeframe = '1D') {
  return useQuery({
    queryKey: ['market', 'chart', symbol, timeframe],
    queryFn: () => api.fetchChart(symbol, timeframe),
    enabled: !!symbol,
    refetchInterval: 60_000,
  })
}

export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: api.fetchStrategies,
    refetchInterval: 30_000,
  })
}

export function useEngineStatus() {
  return useQuery({
    queryKey: ['engine', 'status'],
    queryFn: api.fetchEngineStatus,
  })
}

export function useWatchlist() {
  return useQuery({
    queryKey: ['watchlist'],
    queryFn: api.fetchWatchlist,
  })
}

export function useAddToWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.addToWatchlist,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

export function useRemoveFromWatchlist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.removeFromWatchlist,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist'] }),
  })
}

export function useTrades(limit = 50) {
  return useQuery({
    queryKey: ['trades', limit],
    queryFn: () => api.fetchTrades(limit),
    refetchInterval: 15_000,
  })
}

export function useTradeSummary() {
  return useQuery({
    queryKey: ['trades', 'summary'],
    queryFn: api.fetchTradeSummary,
    refetchInterval: 15_000,
  })
}

export function useEngineControl() {
  const qc = useQueryClient()
  const startMutation = useMutation({
    mutationFn: api.startEngine,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['engine'] }),
  })
  const stopMutation = useMutation({
    mutationFn: api.stopEngine,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['engine'] }),
  })
  return { start: startMutation, stop: stopMutation }
}

export function useEquityHistory(days = 30) {
  return useQuery({
    queryKey: ['portfolio', 'equity-history', days],
    queryFn: () => api.fetchEquityHistory(days),
    refetchInterval: 300_000,
  })
}

export function useBacktestStrategies() {
  return useQuery({
    queryKey: ['backtest', 'strategies'],
    queryFn: api.fetchBacktestStrategies,
  })
}

export function useETFStatus() {
  return useQuery({
    queryKey: ['engine', 'etf'],
    queryFn: api.fetchETFStatus,
    refetchInterval: 30_000,
  })
}
