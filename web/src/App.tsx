import { useState } from 'react'
import { BacktestPage } from './pages/BacktestPage'
import { FactorsPage } from './pages/FactorsPage'
import { FormulaBuilderPage } from './pages/FormulaBuilderPage'
import { RuleBuilderPage } from './pages/RuleBuilderPage'
import { StrategyBuilderPage } from './pages/StrategyBuilderPage'

const TABS = ['팩터', '공식', '규칙', '전략', '백테스트'] as const
type Tab = (typeof TABS)[number]

function App() {
  const [tab, setTab] = useState<Tab>('팩터')

  return (
    <div style={{ padding: '1rem', fontFamily: 'sans-serif' }}>
      <h1>quant-krx GUI</h1>
      <nav style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            style={{ fontWeight: t === tab ? 'bold' : 'normal' }}
          >
            {t}
          </button>
        ))}
      </nav>
      {tab === '팩터' && <FactorsPage />}
      {tab === '공식' && <FormulaBuilderPage />}
      {tab === '규칙' && <RuleBuilderPage />}
      {tab === '전략' && <StrategyBuilderPage />}
      {tab === '백테스트' && <BacktestPage />}
    </div>
  )
}

export default App
