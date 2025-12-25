<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { ChevronLeft, ChevronRight, Download, Plus } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { day as dayLabel } from '@/shared/format'
import { addDays, mondayOf, todayIn } from '@/shared/zone'

import { api, downloadUrl } from '../api'
import BookingPanel from '../components/BookingPanel.vue'
import JournalDay from '../components/JournalDay.vue'
import JournalWeek from '../components/JournalWeek.vue'
import NewBookingPanel from '../components/NewBookingPanel.vue'
import { useShop } from '../context'

const { lang, tz, fmt, business } = useShop()
const view = ref<'day' | 'week'>('day')
const day = ref('')
const showCancelled = ref(false)

watch(
  tz,
  (zone) => {
    if (!day.value && business.data.value) day.value = todayIn(zone)
  },
  { immediate: true },
)

const start = computed(() => (view.value === 'week' ? mondayOf(day.value) : day.value))
const journal = useQuery({
  queryKey: ['admin', 'journal', start, view],
  queryFn: () =>
    api.get<Schemas['JournalOut']>('/api/admin/journal', {
      start: start.value,
      days: view.value === 'week' ? 7 : 1,
    }),
  enabled: computed(() => !!day.value),
  placeholderData: (previous) => previous,
})

const selected = ref<Schemas['AdminBookingOut'] | null>(null)
const panelOpen = ref(false)
const newOpen = ref(false)
const newMaster = ref<number | null>(null)
const newMinutes = ref<number | null>(null)

const visible = computed(() =>
  (journal.data.value?.bookings ?? []).filter((b) => b.status !== 'cancelled'),
)
const dayRevenue = computed(() =>
  visible.value
    .filter((b) => b.status === 'completed' || b.status === 'confirmed')
    .reduce((sum, b) => sum + b.price - b.bonus_spent, 0),
)
const title = computed(() => {
  if (!day.value) return ''
  if (view.value === 'day') return dayLabel(day.value, lang.value, tz.value, true)
  const end = addDays(start.value, 6)
  return `${dayLabel(start.value, lang.value, tz.value)} – ${dayLabel(end, lang.value, tz.value)}`
})

function shift(direction: number): void {
  day.value = addDays(day.value, direction * (view.value === 'week' ? 7 : 1))
}

function openBooking(b: Schemas['AdminBookingOut']): void {
  selected.value = b
  panelOpen.value = true
}

function create(masterId: number | null = null, minutes: number | null = null): void {
  newMaster.value = masterId
  newMinutes.value = minutes
  newOpen.value = true
}

const exportHref = computed(() =>
  downloadUrl('/api/admin/bookings.csv', {
    start: start.value,
    end: view.value === 'week' ? addDays(start.value, 6) : start.value,
  }),
)
</script>

<template>
  <main class="p-4 lg:p-6">
    <header class="flex flex-wrap items-center gap-3">
      <div class="mr-auto">
        <h1 class="font-sign text-3xl font-semibold first-letter:uppercase">{{ title }}</h1>
        <p class="mt-0.5 text-sm text-muted">
          {{ $t('journal.bookings', { n: visible.length }, visible.length) }}
          <template v-if="view === 'day'">
            · {{ $t('journal.revenue') }} <span class="num">{{ fmt(dayRevenue) }}</span></template
          >
        </p>
      </div>
      <div class="flex items-center rounded-lg border border-line bg-surface">
        <button
          type="button"
          class="grid size-9 place-items-center hover:bg-surface-2"
          aria-label="Previous"
          @click="shift(-1)"
        >
          <ChevronLeft :size="18" />
        </button>
        <button
          type="button"
          class="h-9 border-x border-line px-3 text-sm font-semibold hover:bg-surface-2"
          @click="day = todayIn(tz)"
        >
          {{ $t('common.today') }}
        </button>
        <button
          type="button"
          class="grid size-9 place-items-center hover:bg-surface-2"
          aria-label="Next"
          @click="shift(1)"
        >
          <ChevronRight :size="18" />
        </button>
      </div>
      <div
        class="flex rounded-lg border border-line bg-surface p-0.5 text-sm font-semibold"
        role="radiogroup"
      >
        <button
          v-for="option in ['day', 'week'] as const"
          :key="option"
          type="button"
          role="radio"
          :aria-checked="view === option"
          class="rounded-md px-3 py-1.5"
          :class="view === option ? 'bg-ink text-bg' : 'text-muted'"
          @click="view = option"
        >
          {{ $t(`common.${option}`) }}
        </button>
      </div>
      <label class="flex items-center gap-2 text-sm text-muted">
        <input v-model="showCancelled" type="checkbox" class="size-4 accent-[var(--accent)]" />
        {{ $t('status.cancelled') }}
      </label>
      <a
        :href="exportHref"
        class="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-sm font-semibold hover:bg-surface-2"
      >
        <Download :size="16" /> {{ $t('common.export') }}
      </a>
      <button
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-semibold text-accent-ink"
        @click="create()"
      >
        <Plus :size="16" /> {{ $t('journal.new') }}
      </button>
    </header>

    <div
      class="mt-5"
      :class="{ 'opacity-60 transition-opacity': journal.isFetching.value && journal.data.value }"
    >
      <p
        v-if="journal.isError.value"
        class="rounded-xl bg-danger-soft p-4 text-danger"
        role="alert"
      >
        {{ $t('common.error') }}
      </p>
      <div v-else-if="!journal.data.value" class="h-[520px] animate-pulse rounded-2xl bg-surface" />
      <JournalDay
        v-else-if="view === 'day'"
        :journal="journal.data.value"
        :day="day"
        :lang="lang"
        :show-cancelled="showCancelled"
        @open="openBooking"
        @create="create"
      />
      <JournalWeek
        v-else
        :journal="journal.data.value"
        :lang="lang"
        :show-cancelled="showCancelled"
        @open="openBooking"
        @pick="(d) => ((day = d), (view = 'day'))"
      />
    </div>

    <BookingPanel v-model="panelOpen" :booking="selected" />
    <NewBookingPanel
      v-model="newOpen"
      :day="day"
      :master-id="newMaster"
      :minutes="newMinutes"
      @created="openBooking"
    />
  </main>
</template>
