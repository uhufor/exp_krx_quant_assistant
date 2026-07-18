import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { useFactors, useResourceIds } from '../api/hooks'
import { RuleTreeEditor } from '../tree/RuleTreeEditor'
import type { RuleNodeJSON } from '../tree/types'
import { defaultPredicate } from '../tree/types'

type RuleDoc = {
  id: string
  name: string
  version: string
  metadata: Record<string, unknown>
  root: RuleNodeJSON
}

type ValidationResult = { ok: boolean; errors: string[] }

function emptyDoc(id: string, factors: ReturnType<typeof useFactors>): RuleDoc {
  return { id, name: '', version: '1', metadata: {}, root: defaultPredicate(factors) }
}

/** 규칙(Rule) CRUD — 조건 트리는 재귀 편집기, 나머지 필드는 폼(M5, JSON 직접 입력 없음). */
export function RuleBuilderPage() {
  const factors = useFactors()
  const [refreshKey, setRefreshKey] = useState(0)
  const ruleIds = useResourceIds('rules', refreshKey)
  const formulaIds = useResourceIds('formulas', refreshKey)
  const [selectedId, setSelectedId] = useState('')
  const [newId, setNewId] = useState('')
  const [doc, setDoc] = useState<RuleDoc | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [message, setMessage] = useState('')

  const load = (id: string) => {
    setSelectedId(id)
    setValidation(null)
    if (!id) {
      setDoc(null)
      return
    }
    api
      .get<RuleDoc>(`/rules/${id}`)
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
  }

  const handleValidate = () => {
    if (!doc) return
    api
      .post<ValidationResult>('/rules/validate', doc)
      .then(setValidation)
      .catch((e: ApiError) => setMessage(`검증 요청 실패: ${e.message}`))
  }

  const handleSave = () => {
    if (!doc) return
    const id = selectedId || newId
    api
      .put(`/rules/${id}`, doc)
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
      .del(`/rules/${selectedId}`)
      .then(() => {
        setMessage(`'${selectedId}' 삭제 완료`)
        setSelectedId('')
        setDoc(null)
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => setMessage(`삭제 실패(활성 참조 중일 수 있음): ${e.message}`))
  }

  return (
    <div style={{ display: 'flex', gap: '1rem' }}>
      <div style={{ minWidth: '180px' }}>
        <h3>규칙 목록</h3>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {ruleIds.map((id) => (
            <li key={id}>
              <button
                type="button"
                onClick={() => load(id)}
                style={{ fontWeight: id === selectedId ? 'bold' : 'normal' }}
              >
                {id}
              </button>
            </li>
          ))}
        </ul>
        <input placeholder="신규 id" value={newId} onChange={(e) => setNewId(e.target.value)} />
        <button type="button" onClick={startNew}>
          새 규칙
        </button>
      </div>

      <div style={{ flex: 1 }}>
        {doc && (
          <>
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <label>
                이름
                <input
                  value={doc.name}
                  onChange={(e) => setDoc({ ...doc, name: e.target.value })}
                />
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

            <h4>조건</h4>
            <RuleTreeEditor
              value={doc.root}
              onChange={(root) => setDoc({ ...doc, root })}
              factors={factors}
              formulaIds={formulaIds}
            />

            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button type="button" onClick={handleValidate}>
                저장 전 검증
              </button>
              <button type="button" onClick={handleSave}>
                저장
              </button>
              <button type="button" onClick={handleDelete} disabled={!selectedId}>
                삭제
              </button>
            </div>

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
          </>
        )}
        {message && <p>{message}</p>}
      </div>
    </div>
  )
}
