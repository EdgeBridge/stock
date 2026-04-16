import { renderHook, act } from '@testing-library/react-native'
import { useServerConfig } from '../../hooks/useServerConfig'
import * as SecureStore from 'expo-secure-store'

jest.mock('expo-secure-store')
const mockedStore = SecureStore as jest.Mocked<typeof SecureStore>

describe('useServerConfig', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedStore.getItemAsync.mockResolvedValue(null)
    mockedStore.setItemAsync.mockResolvedValue()
    mockedStore.deleteItemAsync.mockResolvedValue()
  })

  it('starts with loading state', () => {
    const { result } = renderHook(() => useServerConfig())
    expect(result.current.isLoading).toBe(true)
  })

  it('loads to default config when no stored data', async () => {
    const { result } = renderHook(() => useServerConfig())
    await act(async () => {})
    expect(result.current.isConfigured).toBe(false)
    expect(result.current.config.serverUrl).toBe('')
    expect(result.current.config.selectedMarket).toBe('US')
  })

  it('loads stored config', async () => {
    const stored = JSON.stringify({
      serverUrl: 'https://test.com',
      apiToken: 'tok',
      selectedMarket: 'KR',
    })
    mockedStore.getItemAsync.mockResolvedValue(stored)

    const { result } = renderHook(() => useServerConfig())
    await act(async () => {})

    expect(result.current.isConfigured).toBe(true)
    expect(result.current.config.serverUrl).toBe('https://test.com')
    expect(result.current.config.selectedMarket).toBe('KR')
  })

  it('saveConfig persists to SecureStore', async () => {
    const { result } = renderHook(() => useServerConfig())
    await act(async () => {})

    await act(async () => {
      await result.current.saveConfig({
        serverUrl: 'https://new.com',
        apiToken: '',
        kisAppKey: '',
        kisAppSecret: '',
        kisAccountNo: '',
        selectedMarket: 'ALL',
      })
    })

    expect(mockedStore.setItemAsync).toHaveBeenCalledWith(
      'stockbot_server_config',
      expect.stringContaining('https://new.com')
    )
    expect(result.current.config.serverUrl).toBe('https://new.com')
  })

  it('clearConfig removes from SecureStore', async () => {
    mockedStore.getItemAsync.mockResolvedValue(JSON.stringify({ serverUrl: 'https://old.com' }))
    const { result } = renderHook(() => useServerConfig())
    await act(async () => {})

    await act(async () => {
      await result.current.clearConfig()
    })

    expect(mockedStore.deleteItemAsync).toHaveBeenCalledWith('stockbot_server_config')
    expect(result.current.isConfigured).toBe(false)
  })

  it('isConfigured true when serverUrl set', async () => {
    mockedStore.getItemAsync.mockResolvedValue(JSON.stringify({ serverUrl: 'https://x.com' }))
    const { result } = renderHook(() => useServerConfig())
    await act(async () => {})
    expect(result.current.isConfigured).toBe(true)
  })
})
