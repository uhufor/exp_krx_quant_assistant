import {
  Alert,
  Badge,
  Card,
  Group,
  Loader,
  Select,
  Table,
  Text,
  TextInput,
} from '@mantine/core'
import { IconAlertCircle, IconSearch } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
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
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    api
      .get<FactorMetadata[]>('/factors')
      .then(setFactors)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const categories = useMemo(
    () => Array.from(new Set(factors.map((f) => f.category))).sort(),
    [factors],
  )

  const filtered = factors.filter((f) => {
    if (category && f.category !== category) return false
    if (search && !`${f.id} ${f.display_name}`.toLowerCase().includes(search.toLowerCase()))
      return false
    return true
  })

  if (error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="팩터 조회 실패">
        {error}
      </Alert>
    )
  }

  if (loading) return <Loader />

  return (
    <Card withBorder padding="md" radius="md">
      <Group mb="md" align="flex-end">
        <TextInput
          label="검색"
          placeholder="id 또는 이름 검색"
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <Select
          label="카테고리"
          placeholder="전체"
          data={categories}
          value={category}
          onChange={setCategory}
          clearable
          w={180}
        />
      </Group>

      <Table striped highlightOnHover withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>id</Table.Th>
            <Table.Th>이름</Table.Th>
            <Table.Th>카테고리</Table.Th>
            <Table.Th>설명</Table.Th>
            <Table.Th>파라미터</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {filtered.map((f) => (
            <Table.Tr key={f.id}>
              <Table.Td>
                <Text ff="monospace" size="sm">
                  {f.id}
                </Text>
              </Table.Td>
              <Table.Td>{f.display_name}</Table.Td>
              <Table.Td>
                <Badge variant="light">{f.category}</Badge>
              </Table.Td>
              <Table.Td>
                <Text size="sm" c="dimmed">
                  {f.description}
                </Text>
              </Table.Td>
              <Table.Td>
                <Group gap={4}>
                  {f.params.map((p) => (
                    <Badge key={p.name} variant="outline" size="sm">
                      {p.name}={p.default}
                    </Badge>
                  ))}
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  )
}
