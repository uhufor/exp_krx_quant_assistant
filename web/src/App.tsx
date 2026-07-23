import {
  ActionIcon,
  AppShell,
  Group,
  Tabs,
  Text,
  Title,
  useMantineColorScheme,
} from '@mantine/core'
import { IconChartLine, IconMoon, IconSun } from '@tabler/icons-react'
import { useState } from 'react'
import { BacktestPage } from './pages/BacktestPage'
import { FactorsPage } from './pages/FactorsPage'
import { FormulaBuilderPage } from './pages/FormulaBuilderPage'
import { RuleBuilderPage } from './pages/RuleBuilderPage'
import { ScreeningBuilderPage } from './pages/ScreeningBuilderPage'
import { StrategyBuilderPage } from './pages/StrategyBuilderPage'

const TABS = [
  { value: 'factors', label: '팩터' },
  { value: 'formulas', label: '공식' },
  { value: 'rules', label: '규칙' },
  { value: 'strategies', label: '전략' },
  { value: 'backtest', label: '백테스트' },
  { value: 'screenings', label: '스크리닝' },
] as const
type Tab = (typeof TABS)[number]['value']

function ColorSchemeToggle() {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()
  return (
    <ActionIcon
      variant="default"
      size="lg"
      onClick={toggleColorScheme}
      aria-label="테마 전환"
    >
      {colorScheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
    </ActionIcon>
  )
}

function App() {
  const [tab, setTab] = useState<Tab>('factors')

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <IconChartLine size={24} />
            <Title order={3}>quant-krx GUI</Title>
            <Text c="dimmed" size="sm">
              로컬 노코드 전략 워크스페이스
            </Text>
          </Group>
          <ColorSchemeToggle />
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Tabs value={tab} onChange={(v) => setTab((v as Tab) ?? 'factors')}>
          <Tabs.List mb="md">
            {TABS.map((t) => (
              <Tabs.Tab key={t.value} value={t.value}>
                {t.label}
              </Tabs.Tab>
            ))}
          </Tabs.List>

          <Tabs.Panel value="factors">
            <FactorsPage />
          </Tabs.Panel>
          <Tabs.Panel value="formulas">
            <FormulaBuilderPage />
          </Tabs.Panel>
          <Tabs.Panel value="rules">
            <RuleBuilderPage />
          </Tabs.Panel>
          <Tabs.Panel value="strategies">
            <StrategyBuilderPage />
          </Tabs.Panel>
          <Tabs.Panel value="backtest">
            <BacktestPage />
          </Tabs.Panel>
          <Tabs.Panel value="screenings">
            <ScreeningBuilderPage />
          </Tabs.Panel>
        </Tabs>
      </AppShell.Main>
    </AppShell>
  )
}

export default App
