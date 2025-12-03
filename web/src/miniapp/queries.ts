import { useQuery } from '@tanstack/vue-query'
import { computed, type MaybeRefOrGetter, toValue } from 'vue'

import type { Schemas } from '@/shared/api/client'

import { api } from './session'

export function useCatalog() {
  return useQuery({
    queryKey: ['catalog'],
    queryFn: () => api.get<Schemas['CatalogOut']>('/api/app/catalog'),
    staleTime: 5 * 60_000,
  })
}

export function useOffers(serviceId: MaybeRefOrGetter<number | null>) {
  return useQuery({
    queryKey: ['offers', serviceId],
    queryFn: () => api.get<Schemas['OfferOut'][]>(`/api/app/services/${toValue(serviceId)}/offers`),
    enabled: computed(() => toValue(serviceId) !== null),
    staleTime: 5 * 60_000,
  })
}

export function useCalendar(
  serviceId: MaybeRefOrGetter<number | null>,
  masterId: MaybeRefOrGetter<number | null>,
) {
  return useQuery({
    queryKey: ['calendar', serviceId, masterId],
    queryFn: () =>
      api.get<Schemas['DayOut'][]>('/api/app/availability/calendar', {
        service_id: toValue(serviceId),
        master_id: toValue(masterId),
      }),
    enabled: computed(() => toValue(serviceId) !== null),
  })
}

export function useSlots(
  serviceId: MaybeRefOrGetter<number | null>,
  day: MaybeRefOrGetter<string | null>,
  masterId: MaybeRefOrGetter<number | null>,
  excludeBookingId: MaybeRefOrGetter<number | null>,
) {
  return useQuery({
    queryKey: ['slots', serviceId, day, masterId, excludeBookingId],
    queryFn: () =>
      api.get<Schemas['SlotOut'][]>('/api/app/availability/slots', {
        service_id: toValue(serviceId),
        day: toValue(day),
        master_id: toValue(masterId),
        exclude_booking_id: toValue(excludeBookingId),
      }),
    enabled: computed(() => toValue(serviceId) !== null && toValue(day) !== null),
  })
}

export function useBookings() {
  return useQuery({
    queryKey: ['bookings'],
    queryFn: () => api.get<Schemas['BookingOut'][]>('/api/app/bookings'),
  })
}

export function useBonusHistory() {
  return useQuery({
    queryKey: ['bonuses'],
    queryFn: () => api.get<Schemas['BonusTxOut'][]>('/api/app/me/bonuses'),
  })
}
