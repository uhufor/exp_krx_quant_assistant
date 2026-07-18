import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'

type FactorMetadata = {
  id: string
  display_name: string
  category: string
  description: string
  params: Array<{ name: string; type: string; default: number; description: string }>
}

/** 팩터 조회 전용 화면(읽기 전용 — 생성/수정/삭제 없음, PRD Non-Goals). */
export function FactorsPage() {
  const [factors, setFactors] = useState<FactorMetadata[]>([])
  const [error, setError] = useState<string>('')

  useEffect(() => {
    api
      .get<FactorMetadata[]>('/factors')
      .then(setFactors)
      .catch((e: ApiError) => setError(e.message))
  }, [])

  if (error) return <p>팩터 조회 실패: {error}</p>

  return (
    <table>
      <thead>
        <tr>
          <th>id</th>
          <th>이름</th>
          <th>카테고리</th>
          <th>설명</th>
          <th>파라미터</th>
        </tr>
      </thead>
      <tbody>
        {factors.map((f) => (
          <tr key={f.id}>
            <td>{f.id}</td>
            <td>{f.display_name}</td>
            <td>{f.category}</td>
            <td>{f.description}</td>
            <td>{f.params.map((p) => `${p.name}=${p.default}`).join(', ')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
