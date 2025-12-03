<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { BellRing } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError, type Schemas } from '@/shared/api/client'
import { day as dayLabel, localDate, money, time } from '@/shared/format'

import Avatar from '../components/Avatar.vue'
import LoadState from '../components/LoadState.vue'
import PageHeader from '../components/PageHeader.vue'
import { useMainAction } from '../composables/mainAction'
import { draft } from '../draft'
import { useCalendar, useCatalog, useOffers, useSlots } from '../queries'
import { api, locale, session } from '../session'
import { haptic } from '../telegram'

const router = useRouter()
const { t } = useI18n()
const queryClient = useQueryClient()
const lang = computed(() => locale())
const tz = computed(() => session.business!.timezone)

if (draft.serviceId === null) void router.replace('/')

const catalog = useCatalog()
const offers = useOffers(() => draft.serviceId)
const calendar = useCalendar(
  () => draft.serviceId,
  () => draft.masterId,
)
const selectedDay = ref<string | null>(draft.startsAt ? localDate(draft.startsAt, tz.value) : null)
const slots = useSlots(
  () => draft.serviceId,
  selectedDay,
  () => draft.masterId,
  () => draft.rescheduleId,
)
const waitlisted = ref(false)
const moving = ref(false)
const error = ref('')

const service = computed(() =>
  catalog.data.value?.categories.flatMap((c) => c.services).find((s) => s.id === draft.serviceId),
)

watch(
  () => calendar.data.value,
  (days) => {
    if (!days) return
    const current = days.find((d) => d.day === selectedDay.value)
    if (!current || current.slots === 0)
      selectedDay.value = days.find((d) => d.slots > 0)?.day ?? null
  },
  { immediate: true },
)

const groups = computed(() => {
  const buckets: Record<'morning' | 'day' | 'evening', Schemas['SlotOut'][]> = {
    morning: [],
    day: [],
    evening: [],
  }
  for (const slot of slots.data.value ?? []) {
    const hour = Number(time(slot.starts_at, tz.value).slice(0, 2))
    buckets[hour < 12 ? 'morning' : hour < 17 ? 'day' : 'evening'].push(slot)
  }
  return (Object.keys(buckets) as (keyof typeof buckets)[])
    .map((key) => ({ key, slots: buckets[key] }))
    .filter((group) => group.slots.length)
})

function pickMaster(id: number | null): void {
  haptic()
  draft.masterId = id
  draft.startsAt = null
}

function pickDay(day: Schemas['DayOut']): void {
  if (!day.slots) return
  haptic()
  selectedDay.value = day.day
  draft.startsAt = null
  waitlisted.value = false
}

function pickSlot(slot: Schemas['SlotOut']): void {
  haptic('light')
  draft.startsAt = slot.starts_at
  draft.slotMasters = slot.master_ids
}

async function joinWaitlist(): Promise<void> {
  if (!selectedDay.value || draft.serviceId === null) return
  await api.post('/api/app/waitlist', {
    service_id: draft.serviceId,
    day: selectedDay.value,
    master_id: draft.masterId,
  })
  haptic('success')
  waitlisted.value = true
}

async function move(): Promise<void> {
  if (draft.rescheduleId === null || !draft.startsAt) return
  moving.value = true
  error.value = ''
  try {
    await api.post(`/api/app/bookings/${draft.rescheduleId}/reschedule`, {
      starts_at: draft.startsAt,
      master_id: draft.masterId,
    })
    haptic('success')
    await queryClient.invalidateQueries({ queryKey: ['bookings'] })
    draft.rescheduleId = null
    void router.replace('/bookings')
  } catch (e) {
    haptic('error')
    error.value =
      e instanceof ApiError && e.status === 409
        ? t('confirm.slotTaken')
        : e instanceof Error
          ? e.message
          : ''
    void slots.refetch()
  } finally {
    moving.value = false
  }
}

useMainAction(
  () => {
    const chosen = draft.startsAt ? time(draft.startsAt, tz.value) : ''
    if (draft.rescheduleId !== null)
      return {
        text: chosen ? t('slots.moveConfirm', { time: chosen }) : t('slots.pickTime'),
        disabled: !chosen,
        loading: moving.value,
      }
    return {
      text: chosen ? t('slots.continue', { time: chosen }) : t('slots.pickTime'),
      disabled: !chosen,
    }
  },
  () => {
    if (draft.rescheduleId !== null) void move()
    else void router.push({ name: 'confirm' })
  },
)
</script>

<template>
  <main>
    <PageHeader
      :title="draft.rescheduleId ? $t('slots.moveTitle') : $t('slots.title')"
      :back="draft.rescheduleId ? '/bookings' : `/service/${draft.serviceId}`"
    />
    <p v-if="service" class="px-4 text-sm text-muted">{{ service.name[lang] }}</p>

    <div
      v-if="!draft.rescheduleId && offers.data.value"
      class="mt-3 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none]"
      role="radiogroup"
      :aria-label="$t('slots.master')"
    >
      <button
        type="button"
        role="radio"
        :aria-checked="draft.masterId === null"
        class="flex shrink-0 items-center gap-2 rounded-full py-1.5 pr-3.5 pl-3.5 text-sm font-semibold"
        :class="draft.masterId === null ? 'bg-ink text-bg' : 'bg-surface text-muted'"
        @click="pickMaster(null)"
      >
        {{ $t('common.anyMaster') }}
      </button>
      <button
        v-for="offer in offers.data.value"
        :key="offer.master.id"
        type="button"
        role="radio"
        :aria-checked="draft.masterId === offer.master.id"
        class="flex shrink-0 items-center gap-2 rounded-full py-1 pr-3.5 pl-1 text-sm font-semibold"
        :class="draft.masterId === offer.master.id ? 'bg-ink text-bg' : 'bg-surface text-muted'"
        @click="pickMaster(offer.master.id)"
      >
        <Avatar
          :src="offer.master.photo_url"
          :name="offer.master.name[lang]"
          :color="offer.master.color"
          :size="26"
        />
        {{ offer.master.name[lang].split(' ')[0] }}
        <span class="font-sign font-semibold num opacity-70">
          {{ money(offer.price, session.business!.currency, lang) }}
        </span>
      </button>
    </div>

    <LoadState
      :loading="calendar.isPending.value"
      :error="calendar.isError.value"
      :lines="2"
      @retry="calendar.refetch()"
    />

    <template v-if="calendar.data.value">
      <p
        v-if="!calendar.data.value.some((d) => d.slots)"
        class="mx-4 mt-6 rounded-2xl bg-surface p-5 text-center text-muted"
      >
        {{ $t('slots.noDays') }}
      </p>
      <div
        v-else
        class="mt-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]"
        role="listbox"
      >
        <button
          v-for="d in calendar.data.value"
          :key="d.day"
          type="button"
          role="option"
          :aria-selected="selectedDay === d.day"
          :disabled="!d.slots"
          class="flex w-[58px] shrink-0 flex-col items-center rounded-[16px] py-2 transition-colors disabled:opacity-35"
          :class="selectedDay === d.day ? 'bg-accent text-accent-ink' : 'bg-surface text-ink'"
          @click="pickDay(d)"
        >
          <span class="text-xs font-semibold opacity-70">
            {{ dayLabel(d.day, lang, tz).split(',')[0] }}
          </span>
          <span class="font-sign text-[26px] leading-tight font-semibold num">
            {{ Number(d.day.slice(8)) }}
          </span>
          <span
            class="h-1.5 w-1.5 rounded-full"
            :class="d.slots ? (selectedDay === d.day ? 'bg-accent-ink' : 'bg-brass') : ''"
          />
        </button>
      </div>

      <section v-if="selectedDay" class="px-4 pt-5" aria-live="polite">
        <h2 class="font-sign text-xl font-semibold first-letter:uppercase">
          {{ dayLabel(selectedDay, lang, tz, true) }}
        </h2>
        <LoadState
          :loading="slots.isFetching.value && !slots.data.value"
          :error="slots.isError.value"
          :lines="1"
          @retry="slots.refetch()"
        />
        <div
          v-if="slots.data.value && !slots.data.value.length"
          class="mt-3 rounded-2xl bg-surface p-5"
        >
          <p class="text-muted">{{ $t('slots.empty') }}</p>
          <p v-if="waitlisted" class="mt-3 text-sm font-semibold text-accent">
            {{ $t('slots.waitlistDone') }}
          </p>
          <button
            v-else
            type="button"
            class="mt-3 flex items-center gap-2 rounded-full bg-accent-soft px-4 py-2 text-sm font-semibold text-accent"
            @click="joinWaitlist"
          >
            <BellRing :size="16" /> {{ $t('slots.waitlist') }}
          </button>
        </div>
        <div v-for="group in groups" :key="group.key" class="mt-4">
          <h3 class="mb-2 text-xs font-semibold text-faint">{{ $t(`slots.${group.key}`) }}</h3>
          <div class="grid grid-cols-4 gap-2">
            <button
              v-for="slot in group.slots"
              :key="slot.starts_at"
              type="button"
              :aria-pressed="draft.startsAt === slot.starts_at"
              class="h-12 rounded-[12px] border font-sign text-[22px] font-semibold num transition-[background-color,transform] active:scale-95"
              :class="
                draft.startsAt === slot.starts_at
                  ? 'border-accent bg-accent text-accent-ink'
                  : 'border-line bg-surface text-ink'
              "
              @click="pickSlot(slot)"
            >
              {{ time(slot.starts_at, tz) }}
            </button>
          </div>
        </div>
        <p v-if="error" class="mt-4 rounded-xl bg-danger-soft p-3 text-sm text-danger" role="alert">
          {{ error }}
        </p>
      </section>
    </template>
  </main>
</template>
