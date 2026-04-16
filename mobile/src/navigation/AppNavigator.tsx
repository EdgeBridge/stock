import React from 'react'
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs'
import { Ionicons } from '@expo/vector-icons'
import DashboardScreen from '../screens/DashboardScreen'
import PositionsScreen from '../screens/PositionsScreen'
import TradesScreen from '../screens/TradesScreen'
import EngineScreen from '../screens/EngineScreen'
import StrategyScreen from '../screens/StrategyScreen'
import { colors } from '../utils/colors'

export type TabParamList = {
  Dashboard: undefined
  Positions: undefined
  Trades: undefined
  Engine: undefined
  Strategy: undefined
}

const Tab = createBottomTabNavigator<TabParamList>()

const ICON_MAP: Record<string, { focused: keyof typeof Ionicons.glyphMap; outline: keyof typeof Ionicons.glyphMap }> = {
  Dashboard: { focused: 'home', outline: 'home-outline' },
  Positions: { focused: 'pie-chart', outline: 'pie-chart-outline' },
  Trades: { focused: 'swap-horizontal', outline: 'swap-horizontal-outline' },
  Engine: { focused: 'cog', outline: 'cog-outline' },
  Strategy: { focused: 'analytics', outline: 'analytics-outline' },
}

interface Props {
  onSettingsPress: () => void
}

export default function AppNavigator({ onSettingsPress }: Props) {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarIcon: ({ focused, size }) => {
          const icons = ICON_MAP[route.name]
          const name = focused ? icons.focused : icons.outline
          return <Ionicons name={name} size={size} color={focused ? colors.gray900 : colors.gray400} />
        },
        tabBarActiveTintColor: colors.gray900,
        tabBarInactiveTintColor: colors.gray400,
        tabBarStyle: {
          backgroundColor: colors.white,
          borderTopColor: colors.gray100,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
      })}
    >
      <Tab.Screen name="Dashboard">
        {() => <DashboardScreen onSettingsPress={onSettingsPress} />}
      </Tab.Screen>
      <Tab.Screen name="Positions" component={PositionsScreen} />
      <Tab.Screen name="Trades" component={TradesScreen} />
      <Tab.Screen name="Engine" component={EngineScreen} />
      <Tab.Screen name="Strategy" component={StrategyScreen} />
    </Tab.Navigator>
  )
}
