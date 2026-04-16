import React, { useState } from 'react'
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native'
import { Ionicons } from '@expo/vector-icons'
import { colors } from '../utils/colors'
import type { ServerConfig } from '../types'

interface Props {
  config: ServerConfig
  onSave: (config: ServerConfig) => Promise<void>
}

const MARKET_OPTIONS = ['US', 'KR', 'ALL'] as const

export default function SetupScreen({ config, onSave }: Props) {
  const [serverUrl, setServerUrl] = useState(config.serverUrl)
  const [apiToken, setApiToken] = useState(config.apiToken)
  const [kisAppKey, setKisAppKey] = useState(config.kisAppKey)
  const [kisAppSecret, setKisAppSecret] = useState(config.kisAppSecret)
  const [kisAccountNo, setKisAccountNo] = useState(config.kisAccountNo)
  const [selectedMarket, setSelectedMarket] = useState(config.selectedMarket || 'US')

  const [showApiToken, setShowApiToken] = useState(false)
  const [showAppSecret, setShowAppSecret] = useState(false)
  const [saving, setSaving] = useState(false)

  const trimmedUrl = serverUrl.trim()
  const isHttps = trimmedUrl.startsWith('https://') || trimmedUrl.startsWith('http://localhost') || trimmedUrl.startsWith('http://192.168.')
  const canConnect = trimmedUrl.length > 0 && isHttps

  const handleConnect = async () => {
    if (!canConnect || saving) return
    setSaving(true)
    try {
      await onSave({
        serverUrl: serverUrl.trim(),
        apiToken: apiToken.trim(),
        kisAppKey: kisAppKey.trim(),
        kisAppSecret: kisAppSecret.trim(),
        kisAccountNo: kisAccountNo.trim(),
        selectedMarket,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>StockBot Setup</Text>
          <Text style={styles.subtitle}>
            Connect to your trading server
          </Text>
        </View>

        {/* Server Connection */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Server Connection</Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>Server URL</Text>
            <TextInput
              style={styles.input}
              value={serverUrl}
              onChangeText={setServerUrl}
              placeholder="https://your-server:8443"
              placeholderTextColor={colors.gray400}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              returnKeyType="next"
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>
              API Token{' '}
              <Text style={styles.labelHint}>(optional)</Text>
            </Text>
            <View style={styles.passwordContainer}>
              <TextInput
                style={styles.passwordInput}
                value={apiToken}
                onChangeText={setApiToken}
                placeholder="Bearer token for auth"
                placeholderTextColor={colors.gray400}
                secureTextEntry={!showApiToken}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
              />
              <TouchableOpacity
                style={styles.eyeButton}
                onPress={() => setShowApiToken(!showApiToken)}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons
                  name={showApiToken ? 'eye-off-outline' : 'eye-outline'}
                  size={20}
                  color={colors.gray400}
                />
              </TouchableOpacity>
            </View>
          </View>
        </View>

        {/* KIS Open API */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>KIS Open API</Text>

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>App Key</Text>
            <TextInput
              style={styles.input}
              value={kisAppKey}
              onChangeText={setKisAppKey}
              placeholder="KIS app key"
              placeholderTextColor={colors.gray400}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>App Secret</Text>
            <View style={styles.passwordContainer}>
              <TextInput
                style={styles.passwordInput}
                value={kisAppSecret}
                onChangeText={setKisAppSecret}
                placeholder="KIS app secret"
                placeholderTextColor={colors.gray400}
                secureTextEntry={!showAppSecret}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
              />
              <TouchableOpacity
                style={styles.eyeButton}
                onPress={() => setShowAppSecret(!showAppSecret)}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons
                  name={showAppSecret ? 'eye-off-outline' : 'eye-outline'}
                  size={20}
                  color={colors.gray400}
                />
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>Account Number</Text>
            <TextInput
              style={styles.input}
              value={kisAccountNo}
              onChangeText={setKisAccountNo}
              placeholder="12345678-01"
              placeholderTextColor={colors.gray400}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="done"
            />
          </View>
        </View>

        {/* Market Selection */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Market</Text>
          <View style={styles.toggleRow}>
            {MARKET_OPTIONS.map((market) => {
              const active = selectedMarket === market
              return (
                <TouchableOpacity
                  key={market}
                  style={[
                    styles.toggleButton,
                    active && styles.toggleButtonActive,
                  ]}
                  onPress={() => setSelectedMarket(market)}
                  activeOpacity={0.7}
                >
                  <Text
                    style={[
                      styles.toggleText,
                      active && styles.toggleTextActive,
                    ]}
                  >
                    {market}
                  </Text>
                </TouchableOpacity>
              )
            })}
          </View>
        </View>

        {/* Connect Button */}
        <TouchableOpacity
          style={[styles.connectButton, !canConnect && styles.connectButtonDisabled]}
          onPress={handleConnect}
          disabled={!canConnect || saving}
          activeOpacity={0.8}
        >
          {saving ? (
            <ActivityIndicator color={colors.white} size="small" />
          ) : (
            <Text style={styles.connectButtonText}>Connect</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  container: {
    flex: 1,
    backgroundColor: colors.gray50,
  },
  content: {
    padding: 24,
    paddingBottom: 48,
  },
  header: {
    marginBottom: 32,
    marginTop: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.gray900,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 15,
    color: colors.gray500,
  },
  section: {
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.gray500,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  fieldGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.gray700,
    marginBottom: 6,
  },
  labelHint: {
    fontSize: 12,
    fontWeight: '400',
    color: colors.gray400,
  },
  input: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.gray200,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 15,
    color: colors.gray900,
  },
  passwordContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.gray200,
    borderRadius: 12,
  },
  passwordInput: {
    flex: 1,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 15,
    color: colors.gray900,
  },
  eyeButton: {
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  toggleRow: {
    flexDirection: 'row',
    gap: 10,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.gray200,
    alignItems: 'center',
  },
  toggleButtonActive: {
    backgroundColor: colors.sky600,
    borderColor: colors.sky600,
  },
  toggleText: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.gray500,
  },
  toggleTextActive: {
    color: colors.white,
  },
  connectButton: {
    backgroundColor: colors.emerald600,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
    minHeight: 52,
  },
  connectButtonDisabled: {
    opacity: 0.4,
  },
  connectButtonText: {
    color: colors.white,
    fontSize: 17,
    fontWeight: '700',
  },
})
