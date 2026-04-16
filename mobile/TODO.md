# StockBot Mobile — TODO

## Phase 1: Foundation (Done)
- [x] Expo + TypeScript project setup
- [x] API client (axios, mirrors web frontend)
- [x] Types (shared with web frontend)
- [x] SecureStore config management (useServerConfig hook)
- [x] 7 shared UI components (MarketPill, MktTag, PctBadge, PnlText, StatCard, InfoRow, SectionCard)
- [x] 5-tab bottom navigation (Dashboard, Positions, Trades, Engine, Strategy)
- [x] Setup screen (server URL, API token, KIS credentials, market selector)
- [x] Dashboard screen (equity hero, quick stats, P&L, holdings, market state, macro)
- [x] Positions screen (filter, summary, position cards)
- [x] Trades screen (filter, trade history)
- [x] Engine screen (start/stop, evaluate, ETF status, tasks)
- [x] Strategy screen (list, expand params, reload)
- [x] Unit tests (11 suites, 96 tests, 100% pass)
- [x] Code review (security, correctness, RN best practices)

## Phase 2: Backend Public Edition
- [ ] Run `backend/scripts/run_public_backtest.py` on server — validate trend_following + macd_histogram params
- [ ] Optimize strategy params based on backtest results (update strategies_public.yaml)
- [ ] Create separate backend deployment config for public edition (systemd service, nginx vhost)
- [ ] Implement backend endpoint for mobile-initiated KIS credential registration
- [ ] Remove unused KIS fields from SetupScreen if backend won't accept them via API

## Phase 3: Real-time Features
- [ ] WebSocket price stream integration (OkHttp → live price updates on Dashboard/Positions)
- [ ] Push notifications for trade execution (expo-notifications)
- [ ] Background task for engine status monitoring

## Phase 4: UI Polish
- [ ] App icon and splash screen design
- [ ] Portfolio equity chart (line chart using react-native-svg or victory-native)
- [ ] Sector heatmap component
- [ ] News sentiment screen
- [ ] Stock chart integration (candlestick)
- [ ] Pull-to-refresh animation polish
- [ ] Dark theme support
- [ ] Localization (KR/EN)

## Phase 5: Build & Distribution
- [ ] EAS Build setup (eas.json)
- [ ] Android APK/AAB build and test on real device
- [ ] iOS build and TestFlight submission
- [ ] App Store / Play Store listing preparation
- [ ] CI/CD pipeline (GitHub Actions → EAS Build)

## Phase 6: Security Hardening
- [ ] Certificate pinning for production server
- [ ] Biometric authentication (expo-local-authentication)
- [ ] Session timeout and auto-lock
- [ ] Obfuscation (Hermes bytecode already helps)

## Known Issues (from code review)
- [ ] DashboardScreen: positions rendered via map() inside ScrollView — convert to FlatList for 20+ positions
- [ ] DashboardScreen: auto-refresh can fire concurrent fetchAll — add guard or AbortController
- [ ] EngineScreen: nested ScrollView for tasks — may cause gesture conflicts on iOS
- [ ] Add tests for AppNavigator and App.tsx root component
