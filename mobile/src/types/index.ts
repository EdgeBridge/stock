// Shared types — mirrored from frontend/src/types/index.ts

export interface PortfolioSummary {
  market: string
  balance: {
    currency: string
    total: number
    available: number
  }
  usd_balance?: {
    total: number
    available: number
  }
  exchange_rate?: number
  positions_count: number
  total_unrealized_pnl: number
  total_unrealized_pnl_pct?: number
  total_equity: number
  available_cash?: number
}

export interface Position {
  symbol: string
  name?: string
  exchange: string
  quantity: number
  avg_price: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  market?: string
  stop_loss_pct?: number
  take_profit_pct?: number
  trailing_active?: boolean
}

export interface EngineStatus {
  running: boolean
  market_phase: string
  kr_market_phase?: string
  tasks?: TaskInfo[]
}

export interface TaskInfo {
  name: string
  interval_sec: number
  phases: string[] | null
  last_run: string | null
  active: boolean
}

export interface PeriodReturn {
  change: number
  pct: number
  base_equity: number
  has_cash_flows?: boolean
}

export interface PortfolioReturns {
  daily: PeriodReturn | null
  weekly: PeriodReturn | null
  monthly: PeriodReturn | null
}

export interface Trade {
  symbol: string
  name?: string
  side: string
  quantity: number
  price: number
  filled_price: number | null
  strategy: string
  status: string
  pnl: number | null
  pnl_pct: number | null
  created_at: string
  market?: string
}

export interface PeriodSummary {
  trades: number
  wins: number
  losses: number
  pnl: number
  pnl_pct: number | null
  win_rate: number
}

export interface TradeSummaryPeriods {
  today: PeriodSummary
  week: PeriodSummary
  month: PeriodSummary
  all_time: PeriodSummary
  total_buys?: number
  total_sells?: number
}

export interface MarketState {
  market_phase?: string
  regime?: string
  spy_price?: number
  vix_level?: number
  kr_market_phase?: string
  kr_regime?: string
  kr_index_price?: number
}

export interface MacroIndicators {
  fed_funds_rate?: number
  treasury_10y?: number
  yield_spread?: number
  cpi_yoy?: number
  unemployment_rate?: number
}

export interface Strategy {
  name: string
  display_name: string
  timeframe: string
  params: Record<string, unknown>
}

export interface ETFManagedPosition {
  reason: string
  sector: string
  hold_days: number
}

export interface ETFStatus {
  status?: string
  last_regime: string | null
  top_sectors: string[]
  managed_positions: Record<string, ETFManagedPosition>
}

export interface ServerConfig {
  serverUrl: string
  apiToken: string
  kisAppKey: string
  kisAppSecret: string
  kisAccountNo: string
  selectedMarket: string
}
