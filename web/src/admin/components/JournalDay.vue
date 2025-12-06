<script setup lang="ts">
import { useIntervalFn } from '@vueuse/core'
import { computed, ref } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { hhmm, minutesOfDay, parseHhmm, todayIn } from '@/shared/zone'

import Avatar from './MasterAvatar.vue'

const props = defineProps<{
  journal: Schemas['JournalOut']
  day: string
  lang: 'ru' | 'en'
  showCancelled: boolean
}>()
const emit = defineEmits<{
  open: [booking: Schemas['AdminBookingOut']]
  create: [masterId: number, minutes: number]
}>()

const PX_PER_MIN = 1.2
const tz = computed(() => props.journal.timezone)
const now = ref(new Date())
useIntervalFn(() => (now.value = new Date()), 60_000)

const shifts = computed(() =>
  props.journal.masters.map((m) => ({
    master: m.master,
    shift: m.shifts.find((s) => s.day === props.day),
  })),
)

const range = computed(() => {
  const works = shifts.value.flatMap((s) => (s.shift?.work ? [s.shift.work] : []))
  if (!works.length) return { start: 10 * 60, end: 21 * 60 }
  const start = Math.min(...works.map((w) => parseHhmm(w.start)))
  const end = Math.max(...works.map((w) => parseHhmm(w.end)))
  return { start: Math.floor(start / 60) * 60, end: Math.ceil(end / 60) * 60 }
})
const height = computed(() => (range.value.end - range.value.start) * PX_PER_MIN)
const hours = computed(() => {
  const list: number[] = []
  for (let m = range.value.start; m <= range.value.end; m += 60) list.push(m)
  return list
})

const y = (minutes: number) => (minutes - range.value.start) * PX_PER_MIN

function bookingsOf(masterId: number) {
  return props.journal.bookings.filter(
    (b) =>
      b.master.id === masterId &&
      sameDay(b.starts_at) &&
      (props.showCancelled || b.status !== 'cancelled'),
  )
}

function sameDay(iso: string): boolean {
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: tz.value }).format(new Date(iso))
  return date === props.day
}

function offsOf(masterId: number) {
  return props.journal.time_off
    .filter((o) => o.master_id === masterId)
    .map((o) => {
      const startsToday = sameDay(o.starts_at)
      const endsToday = sameDay(o.ends_at)
      const from = startsToday ? minutesOfDay(o.starts_at, tz.value) : range.value.start
      const to = endsToday ? minutesOfDay(o.ends_at, tz.value) : range.value.end
      return {
        ...o,
        from: Math.max(from, range.value.start),
        to: Math.min(to || range.value.end, range.value.end),
      }
    })
    .filter((o) => o.to > o.from)
}

function blockStyle(b: Schemas['AdminBookingOut']) {
  const start = minutesOfDay(b.starts_at, tz.value)
  const end = minutesOfDay(b.ends_at, tz.value) || 24 * 60
  return {
    top: `${y(start)}px`,
    height: `${Math.max(18, (end - start) * PX_PER_MIN - 2)}px`,
    '--m': b.master.color,
  }
}

const nowLine = computed(() => {
  if (todayIn(tz.value) !== props.day) return null
  const minutes = minutesOfDay(now.value, tz.value)
  if (minutes < range.value.start || minutes > range.value.end) return null
  return y(minutes)
})

function clickColumn(event: MouseEvent, masterId: number): void {
  const target = event.currentTarget as HTMLElement
  const offset = event.clientY - target.getBoundingClientRect().top
  const minutes = range.value.start + Math.floor(offset / PX_PER_MIN / 15) * 15
  emit('create', masterId, minutes)
}
</script>

<template>
  <div class="overflow-x-auto rounded-2xl border border-line bg-surface">
    <div
      class="grid min-w-max"
      :style="{ gridTemplateColumns: `56px repeat(${shifts.length}, minmax(180px, 1fr))` }"
    >
      <div class="sticky left-0 z-20 border-b border-line bg-surface" />
      <div
        v-for="{ master, shift } in shifts"
        :key="master.id"
        class="flex items-center gap-2.5 border-b border-l border-line px-3 py-2.5"
      >
        <Avatar :master="master" :lang="lang" :size="32" />
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold">{{ master.name[lang] }}</p>
          <p class="text-xs text-muted num">
            {{
              shift?.work
                ? `${shift.work.start.slice(0, 5)}–${shift.work.end.slice(0, 5)}`
                : $t('journal.dayOff')
            }}
          </p>
        </div>
      </div>

      <div class="sticky left-0 z-20 bg-surface" :style="{ height: `${height}px` }">
        <span
          v-for="h in hours"
          :key="h"
          class="absolute right-2 -translate-y-1/2 font-sign text-sm text-faint num"
          :style="{ top: `${y(h)}px` }"
        >
          {{ hhmm(h) }}
        </span>
      </div>

      <div
        v-for="{ master, shift } in shifts"
        :key="master.id"
        class="relative cursor-copy border-l border-line"
        :style="{ height: `${height}px` }"
        @click.self="clickColumn($event, master.id)"
      >
        <div
          v-for="h in hours"
          :key="h"
          class="pointer-events-none absolute inset-x-0 border-t border-line/70"
          :style="{ top: `${y(h)}px` }"
        />
        <template v-if="shift?.work">
          <div
            class="off pointer-events-none absolute inset-x-0 top-0"
            :style="{ height: `${y(parseHhmm(shift.work.start))}px` }"
          />
          <div
            class="off pointer-events-none absolute inset-x-0 bottom-0"
            :style="{ top: `${y(parseHhmm(shift.work.end))}px` }"
          />
          <div
            v-for="br in shift.breaks"
            :key="br.start"
            class="off pointer-events-none absolute inset-x-0 flex items-center justify-center text-[11px] font-medium text-faint"
            :style="{
              top: `${y(parseHhmm(br.start))}px`,
              height: `${(parseHhmm(br.end) - parseHhmm(br.start)) * PX_PER_MIN}px`,
            }"
          >
            {{ $t('journal.break') }}
          </div>
        </template>
        <div
          v-else
          class="off pointer-events-none absolute inset-0 grid place-items-center text-sm text-faint"
        >
          {{ $t('journal.dayOff') }}
        </div>
        <div
          v-for="off in offsOf(master.id)"
          :key="off.id"
          class="off pointer-events-none absolute inset-x-1 flex items-start justify-center rounded-lg pt-2 text-xs font-medium text-muted"
          :style="{ top: `${y(off.from)}px`, height: `${(off.to - off.from) * PX_PER_MIN}px` }"
        >
          {{ off.reason || $t('journal.timeOff') }}
        </div>

        <button
          v-for="b in bookingsOf(master.id)"
          :key="b.id"
          type="button"
          class="booking absolute left-1 overflow-hidden rounded-lg px-2 py-1 text-left text-xs leading-tight transition-shadow hover:shadow-md focus-visible:z-10"
          :class="b.status"
          :style="blockStyle(b)"
          @click="emit('open', b)"
        >
          <span class="flex items-baseline justify-between gap-1">
            <span class="font-sign text-[13px] font-semibold num">
              {{
                new Intl.DateTimeFormat('en-GB', {
                  hour: '2-digit',
                  minute: '2-digit',
                  timeZone: tz,
                }).format(new Date(b.starts_at))
              }}
            </span>
            <span v-if="b.status !== 'confirmed'" class="text-[10px] font-semibold opacity-80">{{
              $t(`status.${b.status}`)
            }}</span>
          </span>
          <span class="block truncate font-semibold">{{ b.client.name }}</span>
          <span class="block truncate opacity-75">{{ b.service.name[lang] }}</span>
        </button>

        <div
          v-if="nowLine !== null"
          class="pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-danger"
          :style="{ top: `${nowLine}px` }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.off {
  background-image: repeating-linear-gradient(
    -45deg,
    transparent 0 6px,
    color-mix(in oklab, var(--line) 55%, transparent) 6px 7px
  );
  background-color: color-mix(in oklab, var(--surface-2) 70%, transparent);
}

.booking {
  /* Absolutely positioned buttons do not stretch between left and right. */
  width: calc(100% - 8px);
  background: color-mix(in oklab, var(--m) 16%, var(--surface));
  border-left: 3px solid var(--m);
  color: var(--ink);
}

.booking.pending_payment {
  border: 1.5px dashed var(--brass);
  border-left: 3px solid var(--m);
}

.booking.completed {
  background: color-mix(in oklab, var(--m) 9%, var(--surface));
}

.booking.no_show {
  opacity: 0.55;
  text-decoration: line-through;
}

.booking.cancelled {
  opacity: 0.4;
  background: var(--surface-2);
}
</style>
