import React, { useState, useCallback } from 'react'
import { ActivityIndicator, View, StyleSheet } from 'react-native'
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context'
import { NavigationContainer } from '@react-navigation/native'
import { StatusBar } from 'expo-status-bar'
import { useServerConfig } from './src/hooks/useServerConfig'
import { initApi } from './src/api/client'
import AppNavigator from './src/navigation/AppNavigator'
import SetupScreen from './src/screens/SetupScreen'
import type { ServerConfig } from './src/types'
import { colors } from './src/utils/colors'

export default function App() {
  const { config, isLoading, isConfigured, saveConfig } = useServerConfig()
  const [showSetup, setShowSetup] = useState(false)

  // Initialize API when config is ready
  React.useEffect(() => {
    if (isConfigured) {
      initApi(config.serverUrl, config.apiToken || undefined)
    }
  }, [config.serverUrl, config.apiToken, isConfigured])

  const handleSave = useCallback(async (newConfig: ServerConfig) => {
    await saveConfig(newConfig)
    initApi(newConfig.serverUrl, newConfig.apiToken || undefined)
    setShowSetup(false)
  }, [saveConfig])

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.gray900} />
      </View>
    )
  }

  if (!isConfigured || showSetup) {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={{ flex: 1, backgroundColor: colors.gray50 }}>
          <StatusBar style="dark" />
          <SetupScreen config={config} onSave={handleSave} />
        </SafeAreaView>
      </SafeAreaProvider>
    )
  }

  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <StatusBar style="dark" />
        <AppNavigator onSettingsPress={() => setShowSetup(true)} />
      </NavigationContainer>
    </SafeAreaProvider>
  )
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.gray50,
  },
})
