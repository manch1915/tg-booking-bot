import { reactive } from 'vue'

import type { Schemas } from '@/shared/api/client'

interface Draft {
  serviceId: number | null
  masterId: number | null
  startsAt: string | null
  slotMasters: number[]
  useBonus: boolean
  method: Schemas['PaymentMethod']
  comment: string
  rescheduleId: number | null
}

const empty = (): Draft => ({
  serviceId: null,
  masterId: null,
  startsAt: null,
  slotMasters: [],
  useBonus: false,
  method: 'card',
  comment: '',
  rescheduleId: null,
})

/** The booking being put together across the service, time and confirm screens. */
export const draft = reactive<Draft>(empty())

export function resetDraft(): void {
  Object.assign(draft, empty())
}
