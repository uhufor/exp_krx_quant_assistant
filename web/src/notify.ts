import { notifications } from '@mantine/notifications'

/** 짧은 결과(저장/삭제/활성화 등) 피드백 — 토스트(PRD 피드백/상태 표시 AC). */
export function notifySuccess(message: string) {
  notifications.show({ message, color: 'green', autoClose: 3000 })
}

export function notifyError(message: string) {
  notifications.show({ message, color: 'red', autoClose: 5000 })
}
