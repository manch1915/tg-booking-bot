<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { CalendarPlus, Check } from 'lucide-vue-next'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import type { Schemas } from '@/shared/api/client'
import { dateTime, money } from '@/shared/format'

import Avatar from '../components/Avatar.vue'
import { useMainAction } from '../composables/mainAction'
import { resetDraft } from '../draft'
import { api, locale, session } from '../session'

const props = defineProps<{ id: number }>()
const router = useRouter()
const { t } = useI18n()
const lang = computed(() => locale())
const business = computed(() => session.business!)

const booking = useQuery({
  queryKey: ['booking', () => props.id],
  queryFn: () => api.get<Schemas['BookingOut']>(`/api/app/bookings/${props.id}`),
})

resetDraft()

function icsStamp(iso: string): string {
  return new Date(iso)
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d{3}/, '')
}

function addToCalendar(): void {
  const b = booking.data.value
  if (!b) return
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Brass and Blade//Booking//EN',
    'BEGIN:VEVENT',
    `UID:booking-${b.id}@brassblade`,
    `DTSTAMP:${icsStamp(new Date().toISOString())}`,
    `DTSTART:${icsStamp(b.starts_at)}`,
    `DTEND:${icsStamp(b.ends_at)}`,
    `SUMMARY:${b.service.name[lang.value]} · ${business.value.name}`,
    `LOCATION:${business.value.address}`,
    `DESCRIPTION:${b.master.name[lang.value]}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ]
  const url = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/calendar' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `brass-blade-${b.id}.ics`
  link.click()
  URL.revokeObjectURL(url)
}

useMainAction(
  () => ({ text: t('done.mine') }),
  () => void router.replace('/bookings'),
)
</script>

<template>
  <main class="px-4 pt-10">
    <div class="grid size-16 place-items-center rounded-full bg-accent text-accent-ink">
      <Check :size="34" :stroke-width="2.5" />
    </div>
    <h1 class="mt-5 font-sign text-[40px] leading-none font-bold">{{ $t('done.title') }}</h1>
    <p class="mt-2 text-muted">{{ $t('done.reminder') }}</p>

    <section v-if="booking.data.value" class="mt-6 rounded-[20px] bg-surface p-4">
      <p class="font-sign text-[28px] leading-tight font-semibold num">
        {{ dateTime(booking.data.value.starts_at, lang, business.timezone) }}
      </p>
      <p class="mt-1 font-semibold">{{ booking.data.value.service.name[lang] }}</p>
      <div class="mt-3 flex items-center gap-3">
        <Avatar
          :src="booking.data.value.master.photo_url"
          :name="booking.data.value.master.name[lang]"
          :color="booking.data.value.master.color"
          :size="36"
        />
        <span class="text-sm">{{ booking.data.value.master.name[lang] }}</span>
        <span class="ml-auto font-sign text-xl font-semibold num">
          {{ money(booking.data.value.price, business.currency, lang) }}
        </span>
      </div>
      <p class="mt-3 border-t border-line pt-3 text-sm text-muted">{{ business.address }}</p>
    </section>

    <div class="mt-4 flex gap-2">
      <button
        type="button"
        class="flex items-center gap-2 rounded-full bg-surface px-4 py-2.5 text-sm font-semibold"
        @click="addToCalendar"
      >
        <CalendarPlus :size="18" :stroke-width="1.75" /> {{ $t('done.calendar') }}
      </button>
      <RouterLink to="/" class="rounded-full px-4 py-2.5 text-sm font-semibold text-accent">
        {{ $t('done.home') }}
      </RouterLink>
    </div>
  </main>
</template>
