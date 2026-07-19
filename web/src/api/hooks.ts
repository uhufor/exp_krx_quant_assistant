import { useEffect, useState } from 'react'
import type { FactorOption } from '../tree/types'
import { api } from './client'

export function useFactors(): FactorOption[] {
  const [factors, setFactors] = useState<FactorOption[]>([])
  useEffect(() => {
    api.get<FactorOption[]>('/factors').then(setFactors).catch(() => setFactors([]))
  }, [])
  return factors
}

export function useResourceIds(basePath: string, refreshKey: number): string[] {
  const [ids, setIds] = useState<string[]>([])
  useEffect(() => {
    api
      .get<Array<{ id: string }>>(`/${basePath}`)
      .then((items) => setIds(items.map((i) => i.id)))
      .catch(() => setIds([]))
  }, [basePath, refreshKey])
  return ids
}

export type TemplateInfo = { template_id: string; origin: 'builtin' | 'user'; name: string }

export function useTemplates(refreshKey: number): TemplateInfo[] {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  useEffect(() => {
    api.get<TemplateInfo[]>('/templates').then(setTemplates).catch(() => setTemplates([]))
  }, [refreshKey])
  return templates
}
