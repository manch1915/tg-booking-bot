import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Schemas } from '@/shared/api/client'
import { money, type Locale } from '@/shared/format'

import { api } from './api'

export function useBusiness() {
  return useQuery({
    queryKey: ['admin', 'settings'],
    queryFn: () => api.get<Schemas['BusinessOut']>('/api/admin/settings'),
    staleTime: 10 * 60_000,
  })
}

export function useMasters() {
  return useQuery({
    queryKey: ['admin', 'masters'],
    queryFn: () => api.get<Schemas['AdminMasterOut'][]>('/api/admin/masters'),
    staleTime: 60_000,
  })
}

export function useServices() {
  return useQuery({
    queryKey: ['admin', 'services'],
    queryFn: () => api.get<Schemas['AdminServiceOut'][]>('/api/admin/services'),
    staleTime: 60_000,
  })
}

/** Locale, shop time zone and money formatting in one place for the admin pages. */
export function useShop() {
  const { locale } = useI18n()
  const business = useBusiness()
  const lang = computed(() => locale.value as Locale)
  const tz = computed(() => business.data.value?.timezone ?? 'UTC')
  const currency = computed(() => business.data.value?.currency ?? 'USD')
  const fmt = (cents: number) => money(cents, currency.value, lang.value)
  return { business, lang, tz, currency, fmt }
}
