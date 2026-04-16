import { useState, useEffect, useCallback } from 'react'
import * as SecureStore from 'expo-secure-store'
import type { ServerConfig } from '../types'

const STORAGE_KEY = 'stockbot_server_config'

const defaultConfig: ServerConfig = {
  serverUrl: '',
  apiToken: '',
  kisAppKey: '',
  kisAppSecret: '',
  kisAccountNo: '',
  selectedMarket: 'US',
}

export function useServerConfig() {
  const [config, setConfig] = useState<ServerConfig>(defaultConfig)
  const [isLoading, setIsLoading] = useState(true)

  const loadConfig = useCallback(async () => {
    try {
      const raw = await SecureStore.getItemAsync(STORAGE_KEY)
      if (raw) {
        setConfig({ ...defaultConfig, ...JSON.parse(raw) })
      }
    } catch {
      // first launch or corrupt data
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  const saveConfig = useCallback(async (newConfig: ServerConfig) => {
    await SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(newConfig))
    setConfig(newConfig)
  }, [])

  const clearConfig = useCallback(async () => {
    await SecureStore.deleteItemAsync(STORAGE_KEY)
    setConfig(defaultConfig)
  }, [])

  const isConfigured = config.serverUrl.length > 0

  return { config, isLoading, isConfigured, saveConfig, clearConfig }
}
