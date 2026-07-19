import { Alert, Button, Group, List, Paper, Stack, TextInput, Title } from '@mantine/core'
import { IconAlertCircle, IconCheck, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { useFactors, useResourceIds } from '../api/hooks'
import { ResourceListPanel } from '../components/ResourceListPanel'
import { notifyError, notifySuccess } from '../notify'
import { FormulaTreeEditor } from '../tree/FormulaTreeEditor'
import type { ExprJSON } from '../tree/types'
import { defaultOperand } from '../tree/types'

type FormulaDoc = {
  id: string
  name: string
  version: string
  output_column: string
  metadata: Record<string, unknown>
  expression: ExprJSON
}

type ValidationResult = { ok: boolean; errors: string[] }

function emptyDoc(id: string, factors: ReturnType<typeof useFactors>): FormulaDoc {
  return {
    id,
    name: '',
    version: '1',
    output_column: 'value',
    metadata: {},
    expression: defaultOperand(factors),
  }
}

/** 공식(Formula) CRUD — 표현식은 트리 편집기, 나머지 필드는 폼(M5, JSON 직접 입력 없음). */
export function FormulaBuilderPage() {
  const factors = useFactors()
  const [refreshKey, setRefreshKey] = useState(0)
  const formulaIds = useResourceIds('formulas', refreshKey)
  const [selectedId, setSelectedId] = useState('')
  const [newId, setNewId] = useState('')
  const [doc, setDoc] = useState<FormulaDoc | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)

  const load = (id: string) => {
    setSelectedId(id)
    setValidation(null)
    if (!id) {
      setDoc(null)
      return
    }
    api
      .get<FormulaDoc>(`/formulas/${id}`)
      .then(setDoc)
      .catch((e: ApiError) => notifyError(`조회 실패: ${e.message}`))
  }

  const startNew = () => {
    if (!newId) {
      notifyError('신규 id를 입력하세요')
      return
    }
    setSelectedId('')
    setDoc(emptyDoc(newId, factors))
    setValidation(null)
  }

  const handleValidate = () => {
    if (!doc) return
    api
      .post<ValidationResult>('/formulas/validate', doc)
      .then(setValidation)
      .catch((e: ApiError) => notifyError(`검증 요청 실패: ${e.message}`))
  }

  const handleSave = () => {
    if (!doc) return
    const id = selectedId || newId
    api
      .put(`/formulas/${id}`, doc)
      .then(() => {
        notifySuccess(`'${id}' 저장 완료`)
        setNewId('')
        setRefreshKey((k) => k + 1)
        load(id)
      })
      .catch((e: ApiError) => notifyError(`저장 실패: ${e.message}`))
  }

  const handleDelete = () => {
    if (!selectedId) return
    api
      .del(`/formulas/${selectedId}`)
      .then(() => {
        notifySuccess(`'${selectedId}' 삭제 완료`)
        setSelectedId('')
        setDoc(null)
        setRefreshKey((k) => k + 1)
      })
      .catch((e: ApiError) => notifyError(`삭제 실패(활성 참조 중일 수 있음): ${e.message}`))
  }

  return (
    <Group align="flex-start" gap="md">
      <ResourceListPanel
        title="공식 목록"
        ids={formulaIds}
        selectedId={selectedId}
        onSelect={load}
        newId={newId}
        onNewIdChange={setNewId}
        onStartNew={startNew}
        newLabel="새 공식"
      />

      {doc && (
        <Paper withBorder p="md" radius="md" style={{ flex: 1 }}>
          <Stack gap="md">
            <Group align="flex-end">
              <TextInput label="ID" value={doc.id} disabled w={180} />
              <TextInput
                label="이름"
                value={doc.name}
                onChange={(e) => setDoc({ ...doc, name: e.currentTarget.value })}
              />
              <TextInput
                label="버전"
                value={doc.version}
                onChange={(e) => setDoc({ ...doc, version: e.currentTarget.value })}
                w={80}
              />
              <TextInput
                label="출력 컬럼"
                value={doc.output_column}
                onChange={(e) => setDoc({ ...doc, output_column: e.currentTarget.value })}
                w={140}
              />
            </Group>

            <div>
              <Title order={5} mb="xs">
                표현식
              </Title>
              <FormulaTreeEditor
                value={doc.expression}
                onChange={(expression) => setDoc({ ...doc, expression })}
                factors={factors}
                formulaIds={formulaIds.filter((id) => id !== doc.id)}
              />
            </div>

            <Group>
              <Button variant="default" onClick={handleValidate}>
                저장 전 검증
              </Button>
              <Button onClick={handleSave}>저장</Button>
              <Button
                color="red"
                variant="outline"
                leftSection={<IconTrash size={14} />}
                onClick={handleDelete}
                disabled={!selectedId}
              >
                삭제
              </Button>
            </Group>

            {validation && (
              <Alert
                icon={validation.ok ? <IconCheck size={16} /> : <IconAlertCircle size={16} />}
                color={validation.ok ? 'green' : 'red'}
                title={validation.ok ? '검증 통과' : '검증 실패'}
              >
                {!validation.ok && (
                  <List size="sm">
                    {validation.errors.map((err) => (
                      <List.Item key={err}>{err}</List.Item>
                    ))}
                  </List>
                )}
              </Alert>
            )}
          </Stack>
        </Paper>
      )}
    </Group>
  )
}
