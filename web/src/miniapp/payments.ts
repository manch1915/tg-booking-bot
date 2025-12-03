import type { Schemas } from '@/shared/api/client'

import { api } from './session'

const intents = new Map<number, Schemas['PaymentIntentOut']>()

export function rememberIntent(bookingId: number, intent: Schemas['PaymentIntentOut']): void {
  intents.set(bookingId, intent)
}

/** The intent returned by the booking call, or a fresh one when the page was reopened. */
export async function intentFor(bookingId: number): Promise<Schemas['PaymentIntentOut']> {
  const known = intents.get(bookingId)
  if (known) return known
  const fresh = await api.post<Schemas['PaymentIntentOut']>(`/api/app/bookings/${bookingId}/pay`)
  intents.set(bookingId, fresh)
  return fresh
}

export function forgetIntent(bookingId: number): void {
  intents.delete(bookingId)
}
