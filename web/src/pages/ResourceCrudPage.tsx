import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'

type ResourceCrudPageProps = {
  /** "formulas" | "rules" | "strategies" — /api/{basePath} */
  basePath: string
  label: string
}

type ValidationResult = { ok: boolean; errors: string[] }

/**
 * 공식/규칙/전략 CRUD 최소 UI(M3, JSON textarea 기반 초기 버전).
 * 트리 시각 편집기는 M5에서 이 컴포넌트를 대체/보강한다(PRD: JSON 직접 입력 없이도
 * 조작 가능해야 하므로 이 버전은 임시 골격이며 최종 UI가 아니다).
 */
export function ResourceCrudPage({ basePath, label }: ResourceCrudPageProps) {
  const [ids, setIds] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [newId, setNewId] = useState('')
  const [draft, setDraft] = useState('{}')
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [message, setMessage] = useState<string>('')

  const refreshList = () => {
    api
      .get<Array<{ id: string }>>(`/${basePath}`)
      .then((items) => setIds(items.map((i) => i.id)))
      .catch((e: ApiError) => setMessage(`목록 조회 실패: ${e.message}`))
  }

  useEffect(refreshList, [basePath])

  const loadSelected = (id: string) => {
    setSelectedId(id)
    setValidation(null)
    if (!id) {
      setDraft('{}')
      return
    }
    api
      .get<object>(`/${basePath}/${id}`)
      .then((body) => setDraft(JSON.stringify(body, null, 2)))
      .catch((e: ApiError) => setMessage(`조회 실패: ${e.message}`))
  }

  const handleValidate = () => {
    try {
      const body = JSON.parse(draft)
      api
        .post<ValidationResult>(`/${basePath}/validate`, body)
        .then(setValidation)
        .catch((e: ApiError) => setMessage(`검증 요청 실패: ${e.message}`))
    } catch {
      setValidation({ ok: false, errors: ['JSON 파싱 실패 — 문법을 확인하세요'] })
    }
  }

  const handleSave = () => {
    const id = selectedId || newId
    if (!id) {
      setMessage('id를 지정하세요(신규 id 입력 또는 목록에서 선택)')
      return
    }
    try {
      const body = JSON.parse(draft)
      api
        .put(`/${basePath}/${id}`, body)
        .then(() => {
          setMessage(`'${id}' 저장 완료`)
          setNewId('')
          refreshList()
          loadSelected(id)
        })
        .catch((e: ApiError) => setMessage(`저장 실패: ${e.message}`))
    } catch {
      setMessage('JSON 파싱 실패 — 문법을 확인하세요')
    }
  }

  const handleDelete = () => {
    if (!selectedId) return
    api
      .del(`/${basePath}/${selectedId}`)
      .then(() => {
        setMessage(`'${selectedId}' 삭제 완료`)
        setSelectedId('')
        setDraft('{}')
        refreshList()
      })
      .catch((e: ApiError) => setMessage(`삭제 실패(활성 참조 중일 수 있음): ${e.message}`))
  }

  return (
    <div style={{ display: 'flex', gap: '1rem' }}>
      <div style={{ minWidth: '180px' }}>
        <h3>{label} 목록</h3>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {ids.map((id) => (
            <li key={id}>
              <button
                type="button"
                onClick={() => loadSelected(id)}
                style={{ fontWeight: id === selectedId ? 'bold' : 'normal' }}
              >
                {id}
              </button>
            </li>
          ))}
        </ul>
        <input
          placeholder="신규 id"
          value={newId}
          onChange={(e) => {
            setNewId(e.target.value)
            setSelectedId('')
          }}
        />
      </div>
      <div style={{ flex: 1 }}>
        <textarea
          rows={20}
          style={{ width: '100%', fontFamily: 'monospace' }}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
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
        {message && <p>{message}</p>}
      </div>
    </div>
  )
}
