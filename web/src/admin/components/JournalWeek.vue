<script setup lang="ts">
import { computed } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { day as dayLabel, time } from '@/shared/format'
import { todayIn } from '@/shared/zone'

const props = defineProps<{
  journal: Schemas['JournalOut']
  lang: 'ru' | 'en'
  showCancelled: boolean
}>()
const emit = defineEmits<{
  open: [booking: Schemas['AdminBookingOut']]
  pick: [day: string]
}>()

const tz = computed(() => props.journal.timezone)
const localDay = (iso: string) =>
  new Intl.DateTimeFormat('en-CA', { timeZone: tz.value }).format(new Date(iso))

const columns = computed(() =>
  props.journal.days.map((day) => ({
    day,
    bookings: props.journal.bookings.filter(
      (b) => localDay(b.starts_at) === day && (props.showCancelled || b.status !== 'cancelled'),
    ),
  })),
)
</script>

<template>
  <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
    <section
      v-for="column in columns"
      :key="column.day"
      class="flex min-h-40 flex-col rounded-2xl border border-line bg-surface"
    >
      <button
        type="button"
        class="flex items-baseline justify-between border-b border-line px-3 py-2 text-left hover:bg-surface-2"
        :class="column.day === todayIn(tz) ? 'text-accent' : ''"
        @click="emit('pick', column.day)"
      >
        <span class="font-sign text-lg font-semibold first-letter:uppercase">
          {{ dayLabel(column.day, lang, tz) }}
        </span>
        <span class="text-xs text-muted num">{{ column.bookings.length }}</span>
      </button>
      <ul class="flex-1 space-y-1 p-2">
        <li v-for="b in column.bookings" :key="b.id">
          <button
            type="button"
            class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-surface-2"
            :class="{ 'opacity-45': b.status === 'cancelled' || b.status === 'no_show' }"
            @click="emit('open', b)"
          >
            <span class="h-6 w-1 shrink-0 rounded-full" :style="{ background: b.master.color }" />
            <span class="font-sign text-sm font-semibold num">{{ time(b.starts_at, tz) }}</span>
            <span class="min-w-0 flex-1 truncate">{{ b.client.name }}</span>
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
