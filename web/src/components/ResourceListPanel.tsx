import { Button, NavLink, Paper, ScrollArea, Stack, Text, TextInput } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import type { ReactNode } from 'react'

type ResourceListPanelProps = {
  title: string
  ids: string[]
  selectedId: string
  onSelect: (id: string) => void
  newId: string
  onNewIdChange: (v: string) => void
  onStartNew: () => void
  newLabel?: string
  children?: ReactNode
}

/** 공식/규칙/전략 빌더 페이지가 공유하는 목록+신규생성 패널. */
export function ResourceListPanel({
  title,
  ids,
  selectedId,
  onSelect,
  newId,
  onNewIdChange,
  onStartNew,
  newLabel,
  children,
}: ResourceListPanelProps) {
  return (
    <Paper withBorder p="sm" radius="md" w={240} style={{ flexShrink: 0, alignSelf: 'flex-start' }}>
      <Stack gap="xs">
        <Text fw={600} size="sm">
          {title}
        </Text>
        <ScrollArea.Autosize mah={320}>
          <Stack gap={2}>
            {ids.map((id) => (
              <NavLink
                key={id}
                label={id}
                active={id === selectedId}
                onClick={() => onSelect(id)}
                variant="light"
                py={4}
              />
            ))}
            {ids.length === 0 && (
              <Text size="xs" c="dimmed" ta="center" py="sm">
                등록된 항목 없음
              </Text>
            )}
          </Stack>
        </ScrollArea.Autosize>
        <TextInput
          label="신규 id"
          description="소문자로 시작, 소문자·숫자·_ 만 사용(예: my_formula_1)"
          placeholder="my_formula_1"
          size="sm"
          value={newId}
          onChange={(e) => onNewIdChange(e.currentTarget.value)}
        />
        <Button
          leftSection={<IconPlus size={14} />}
          onClick={onStartNew}
          size="sm"
          variant="light"
          fullWidth
        >
          {newLabel ?? '새로 만들기'}
        </Button>
        {children}
      </Stack>
    </Paper>
  )
}
