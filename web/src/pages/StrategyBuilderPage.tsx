import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { useFactors, useResourceIds, useTemplates } from '../api/hooks'
import type { TemplateInfo } from '../api/hooks'
import type { FactorOption } from '../tree/types'

type FactorRefJSON = { factor_id: string; params: Record<string, number> }
type RuleBindingJSON = { roles: { entry: string[]; exit: string[] } }
type StrategyDoc = {
  id: string
  name: string
  version: string
  factor_refs: FactorRefJSON[]
  universe: { symbols: string[] }
  rule: RuleBindingJSON | null
  metadata: Record<string, unknown>
}

type ValidationResult = { ok: boolean; errors: string[] }

function emptyDoc(id: string, factors: FactorOption[]): StrategyDoc {
  const first = factors[0]
  return {
    id,
    name: '',
    version: '1',
    factor_refs: first ? [{ factor_id: first.id, params: {} }] : [],
    universe: { symbols: [] },
    rule: null, // 초안 — RuleBinding은 entry가 비어있으면 저장이 거부되므로 null(초안)이 유효한 기본값
    metadata: {},
  }
}

/** 전략(Strategy) CRUD — factor_refs/universe/rule 참조를 폼으로 편집(JSON 직접 작성 없음, PRD CRUD AC1). */
export function StrategyBuilderPage() {
  const factors = useFactors()
  const [refreshKey, setRefreshKey] = useState(0)
  const strategyIds = useResourceIds('strategies', refreshKey)
  const ruleIds = useResourceIds('rules', refreshKey)
  const templates = useTemplates(refreshKey)
  const [selectedId, setSelectedId] = useState('')
  const [newId, setNewId] = useState('')
  const [doc, setDoc] = useState<StrategyDoc | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [message, setMessage] = useState('')
  const [activeState, setActiveState] = useState<boolean | null>(null)
  const [saveAsTemplateId, setSaveAsTemplateId] = useState('')

  const load = (id: string) => {
    setSelectedId(id)
    setValidation(null)
    setActiveState(null)
    if (!id) {
      setDoc(null)
      return
    }
    api
      .get<StrategyDoc>(`/strategies/${id}`)
      .then(setDoc)
      .catch((e: ApiError) => setMessage(`조회 실패: ${e.message}`))
  }

  const startNew = () => {
    if (!newId) {
      setMessage('신규 id를 입력하세요')
      return
    }
    setSelectedId('')
    setDoc(emptyDoc(newId, factors))
    setValidation(null)
    setActiveState(null)
  }

  const handleCreateFromTemplate = (templateId: string) => {
    if (!templateId) return
    if (!newId) {
      setMessage('템플릿에서 생성할 신규 id를 입력하세요')
      return
    }
    api
      .post<{ id: string }>(`/templates/from/${templateId}`, { new_id: newId })
      .then((defn) => {
        setMessage(`템플릿 '${templateId}'에서 '${defn.id}' 생성 완료`)
        setNewId('')
        setRefreshKey((k) => k + 1)
        load(defn.id)
      })
      .catch((e: ApiError) => setMessage(`템플릿 생성 실패: ${e.message}`))
  }

  const handleSaveAsTemplate = () => {
    if (!selectedId) return
    if (!saveAsTemplateId) {
      setMessage('저장할 template id를 입력하세요')
      return
    }
    api
      .post('/templates', { strategy_id: selectedId, template_id: saveAsTemplateId })
      .then(() => {
        setMessage(`'${selectedId}'을(를) 템플릿 '${saveAsTemplateId}'로 저장 완료`)
        setSaveAsTemplateId('')
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => setMessage(`템플릿 저장 실패: ${e.message}`))
  }

  const handleValidate = () => {
    if (!doc) return
    api
      .post<ValidationResult>('/strategies/validate', doc)
      .then(setValidation)
      .catch((e: ApiError) => setMessage(`검증 요청 실패: ${e.message}`))
  }

  const handleSave = () => {
    if (!doc) return
    const id = selectedId || newId
    api
      .put(`/strategies/${id}`, doc)
      .then(() => {
        setMessage(`'${id}' 저장 완료`)
        setNewId('')
        setRefreshKey((k) => k + 1)
        load(id)
      })
      .catch((e: ApiError) => setMessage(`저장 실패: ${e.message}`))
  }

  const handleDelete = () => {
    if (!selectedId) return
    api
      .del(`/strategies/${selectedId}`)
      .then(() => {
        setMessage(`'${selectedId}' 삭제 완료`)
        setSelectedId('')
        setDoc(null)
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => setMessage(`삭제 실패(활성 참조 중일 수 있음): ${e.message}`))
  }

  const handleActivate = (active: boolean) => {
    if (!selectedId) return
    api
      .post(`/strategies/${selectedId}/${active ? 'activate' : 'deactivate'}`)
      .then(() => {
        setActiveState(active)
        setMessage(`'${selectedId}' ${active ? '활성화' : '비활성화'} 완료`)
      })
      .catch((e: ApiError) => setMessage(`전환 실패: ${e.message}`))
  }

  const handleExport = () => {
    if (!selectedId) return
    api
      .get<object>(`/strategies/${selectedId}/export`)
      .then((bundle) => {
        const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${selectedId}.json`
        a.click()
        URL.revokeObjectURL(url)
      })
      .catch((e: ApiError) => setMessage(`Export 실패: ${e.message}`))
  }

  const handleImport = (file: File) => {
    file
      .text()
      .then((text) => api.post('/strategies/import', JSON.parse(text)))
      .then(() => {
        setMessage('Import 완료')
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError | Error) => setMessage(`Import 실패: ${e.message}`))
  }

  if (!doc) {
    return (
      <div style={{ display: 'flex', gap: '1rem' }}>
        <StrategyList
          strategyIds={strategyIds}
          selectedId={selectedId}
          onSelect={load}
          newId={newId}
          onNewIdChange={setNewId}
          onStartNew={startNew}
          onImport={handleImport}
          templates={templates}
          onCreateFromTemplate={handleCreateFromTemplate}
        />
        <div style={{ flex: 1 }}>{message && <p>{message}</p>}</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', gap: '1rem' }}>
      <StrategyList
        strategyIds={strategyIds}
        selectedId={selectedId}
        onSelect={load}
        newId={newId}
        onNewIdChange={setNewId}
        onStartNew={startNew}
        onImport={handleImport}
        templates={templates}
        onCreateFromTemplate={handleCreateFromTemplate}
      />

      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <label>
            이름
            <input value={doc.name} onChange={(e) => setDoc({ ...doc, name: e.target.value })} />
          </label>
          <label>
            버전
            <input
              value={doc.version}
              onChange={(e) => setDoc({ ...doc, version: e.target.value })}
              style={{ width: '3rem' }}
            />
          </label>
        </div>

        <FactorRefsEditor
          value={doc.factor_refs}
          onChange={(factor_refs) => setDoc({ ...doc, factor_refs })}
          factors={factors}
        />

        <SymbolsEditor
          value={doc.universe.symbols}
          onChange={(symbols) => setDoc({ ...doc, universe: { symbols } })}
        />

        <RuleBindingEditor
          value={doc.rule}
          onChange={(rule) => setDoc({ ...doc, rule })}
          ruleIds={ruleIds}
        />

        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
          <button type="button" onClick={handleValidate}>
            저장 전 검증
          </button>
          <button type="button" onClick={handleSave}>
            저장
          </button>
          <button type="button" onClick={handleDelete} disabled={!selectedId}>
            삭제
          </button>
          <button type="button" onClick={() => handleActivate(true)} disabled={!selectedId}>
            활성화
          </button>
          <button type="button" onClick={() => handleActivate(false)} disabled={!selectedId}>
            비활성화
          </button>
          <button type="button" onClick={handleExport} disabled={!selectedId}>
            Export
          </button>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.5rem' }}>
          <input
            placeholder="template id"
            value={saveAsTemplateId}
            onChange={(e) => setSaveAsTemplateId(e.target.value)}
            disabled={!selectedId}
          />
          <button type="button" onClick={handleSaveAsTemplate} disabled={!selectedId}>
            템플릿으로 저장
          </button>
        </div>

        {activeState != null && <p>현재 상태: {activeState ? '활성' : '비활성'}</p>}

        {validation && (
          <div>
            <strong>검증 결과: {validation.ok ? '통과' : '실패'}</strong>
            <ul>
              {validation.errors.map((err) => (
                <li key={err}>{err}</li>
              ))}
            </ul>
          </div>
        )}
        {message && <p>{message}</p>}
      </div>
    </div>
  )
}

function StrategyList({
  strategyIds,
  selectedId,
  onSelect,
  newId,
  onNewIdChange,
  onStartNew,
  onImport,
  templates,
  onCreateFromTemplate,
}: {
  strategyIds: string[]
  selectedId: string
  onSelect: (id: string) => void
  newId: string
  onNewIdChange: (v: string) => void
  onStartNew: () => void
  onImport: (file: File) => void
  templates: TemplateInfo[]
  onCreateFromTemplate: (templateId: string) => void
}) {
  return (
    <div style={{ minWidth: '180px' }}>
      <h3>전략 목록</h3>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {strategyIds.map((id) => (
          <li key={id}>
            <button
              type="button"
              onClick={() => onSelect(id)}
              style={{ fontWeight: id === selectedId ? 'bold' : 'normal' }}
            >
              {id}
            </button>
          </li>
        ))}
      </ul>
      <input placeholder="신규 id" value={newId} onChange={(e) => onNewIdChange(e.target.value)} />
      <button type="button" onClick={onStartNew}>
        새 전략(빈 정의)
      </button>
      <div style={{ marginTop: '0.5rem' }}>
        <select value="" onChange={(e) => e.target.value && onCreateFromTemplate(e.target.value)}>
          <option value="">템플릿에서 생성...</option>
          {templates.map((t) => (
            <option key={t.template_id} value={t.template_id}>
              {t.name}({t.template_id}, {t.origin})
            </option>
          ))}
        </select>
      </div>
      <div style={{ marginTop: '0.5rem' }}>
        <label>
          Import
          <input
            type="file"
            accept="application/json"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) onImport(file)
              e.target.value = ''
            }}
          />
        </label>
      </div>
    </div>
  )
}

function FactorRefsEditor({
  value,
  onChange,
  factors,
}: {
  value: FactorRefJSON[]
  onChange: (v: FactorRefJSON[]) => void
  factors: FactorOption[]
}) {
  const updateRow = (i: number, row: FactorRefJSON) => {
    const next = [...value]
    next[i] = row
    onChange(next)
  }
  const removeRow = (i: number) => onChange(value.filter((_, idx) => idx !== i))
  const addRow = () => {
    const first = factors[0]
    onChange([...value, { factor_id: first?.id ?? '', params: {} }])
  }

  return (
    <div>
      <h4>팩터 참조(factor_refs)</h4>
      {value.map((ref, i) => {
        const selected = factors.find((f) => f.id === ref.factor_id)
        return (
          // eslint-disable-next-line react/no-array-index-key
          <div key={i} style={{ display: 'flex', gap: '0.25rem', alignItems: 'center', marginBottom: '0.25rem' }}>
            <select
              value={ref.factor_id}
              onChange={(e) => updateRow(i, { factor_id: e.target.value, params: {} })}
            >
              {factors.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.display_name}({f.id})
                </option>
              ))}
            </select>
            {selected?.params.map((p) => (
              <label key={p.name} style={{ fontSize: '0.85em' }}>
                {p.name}
                <input
                  type="number"
                  value={ref.params[p.name] ?? p.default}
                  onChange={(e) =>
                    updateRow(i, {
                      ...ref,
                      params: { ...ref.params, [p.name]: Number(e.target.value) },
                    })
                  }
                  style={{ width: '4rem' }}
                />
              </label>
            ))}
            <button type="button" onClick={() => removeRow(i)}>
              제거
            </button>
          </div>
        )
      })}
      <button type="button" onClick={addRow}>
        + 팩터 추가
      </button>
    </div>
  )
}

function SymbolsEditor({
  value,
  onChange,
}: {
  value: string[]
  onChange: (v: string[]) => void
}) {
  const [draft, setDraft] = useState('')

  const add = () => {
    if (draft && !value.includes(draft)) onChange([...value, draft])
    setDraft('')
  }
  const remove = (symbol: string) => onChange(value.filter((s) => s !== symbol))

  return (
    <div>
      <h4>대상 종목(universe.symbols, 비어있으면 watchlist 전체)</h4>
      <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', marginBottom: '0.25rem' }}>
        {value.map((s) => (
          <span key={s} style={{ border: '1px solid #ccc', borderRadius: 4, padding: '0 0.4rem' }}>
            {s}{' '}
            <button type="button" onClick={() => remove(s)}>
              ×
            </button>
          </span>
        ))}
      </div>
      <input
        placeholder="종목코드 6자리(예: 005930)"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        style={{ width: '10rem' }}
      />
      <button type="button" onClick={add}>
        추가
      </button>
    </div>
  )
}

function RuleBindingEditor({
  value,
  onChange,
  ruleIds,
}: {
  value: RuleBindingJSON | null
  onChange: (v: RuleBindingJSON | null) => void
  ruleIds: string[]
}) {
  const isDraft = value === null

  const addRole = (role: 'entry' | 'exit', ruleId: string) => {
    if (!value || !ruleId || value.roles[role].includes(ruleId)) return
    onChange({ roles: { ...value.roles, [role]: [...value.roles[role], ruleId] } })
  }
  const removeRole = (role: 'entry' | 'exit', ruleId: string) => {
    if (!value) return
    onChange({ roles: { ...value.roles, [role]: value.roles[role].filter((id) => id !== ruleId) } })
  }

  return (
    <div>
      <h4>규칙 바인딩(rule)</h4>
      <label>
        <input
          type="checkbox"
          checked={isDraft}
          onChange={(e) =>
            onChange(e.target.checked ? null : { roles: { entry: [], exit: [] } })
          }
        />
        초안(규칙 미지정 — 활성화/백테스트 불가)
      </label>

      {!isDraft && value && (
        <>
          <RoleEditor
            label="진입(entry, 최소 1개 필수)"
            selected={value.roles.entry}
            ruleIds={ruleIds}
            onAdd={(id) => addRole('entry', id)}
            onRemove={(id) => removeRole('entry', id)}
          />
          <RoleEditor
            label="청산(exit, 생략 가능)"
            selected={value.roles.exit}
            ruleIds={ruleIds}
            onAdd={(id) => addRole('exit', id)}
            onRemove={(id) => removeRole('exit', id)}
          />
        </>
      )}
    </div>
  )
}

function RoleEditor({
  label,
  selected,
  ruleIds,
  onAdd,
  onRemove,
}: {
  label: string
  selected: string[]
  ruleIds: string[]
  onAdd: (id: string) => void
  onRemove: (id: string) => void
}) {
  const available = ruleIds.filter((id) => !selected.includes(id))
  return (
    <div style={{ marginBottom: '0.25rem' }}>
      <div>{label}</div>
      <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap', marginBottom: '0.25rem' }}>
        {selected.map((id) => (
          <span key={id} style={{ border: '1px solid #ccc', borderRadius: 4, padding: '0 0.4rem' }}>
            {id}{' '}
            <button type="button" onClick={() => onRemove(id)}>
              ×
            </button>
          </span>
        ))}
      </div>
      <select value="" onChange={(e) => e.target.value && onAdd(e.target.value)}>
        <option value="">규칙 추가...</option>
        {available.map((id) => (
          <option key={id} value={id}>
            {id}
          </option>
        ))}
      </select>
    </div>
  )
}
