import { createContext, useContext, useState, type ReactNode } from 'react'

type Market = 'US' | 'KR'

interface MarketContextType {
  market: Market
  setMarket: (m: Market) => void
  currency: string
}

const MarketContext = createContext<MarketContextType>({
  market: 'US',
  setMarket: () => {},
  currency: 'USD',
})

export function MarketProvider({ children }: { children: ReactNode }) {
  const [market, setMarket] = useState<Market>('US')
  const currency = market === 'KR' ? 'KRW' : 'USD'
  return (
    <MarketContext.Provider value={{ market, setMarket, currency }}>
      {children}
    </MarketContext.Provider>
  )
}

export function useMarket() {
  return useContext(MarketContext)
}
