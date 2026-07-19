import { Alert, Button, Group, List, Paper, Stack, TextInput, Title } from '@mantine/core'
import { IconAlertCircle, IconCheck, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import { api, ApiError } from '../api/client'
import { useFactors, useResourceIds } from '../api/hooks'
import { ResourceListPanel } from '../components/ResourceListPanel'
import { notifyError, notifySuccess } from '../notify'
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
      .post<ValidationResult>('/rules/validate', doc)
      .then(setValidation)
      .catch((e: ApiError) => notifyError(`검증 요청 실패: ${e.message}`))
  }

  const handleSave = () => {
    if (!doc) return
    const id = selectedId || newId
    api
      .put(`/rules/${id}`, doc)
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
      .del(`/rules/${selectedId}`)
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
        title="규칙 목록"
        ids={ruleIds}
        selectedId={selectedId}
        onSelect={load}
        newId={newId}
        onNewIdChange={setNewId}
        onStartNew={startNew}
        newLabel="새 규칙"
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
            </Group>

            <div>
              <Title order={5} mb="xs">
                조건
              </Title>
              <RuleTreeEditor
                value={doc.root}
                onChange={(root) => setDoc({ ...doc, root })}
                factors={factors}
                formulaIds={formulaIds}
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
