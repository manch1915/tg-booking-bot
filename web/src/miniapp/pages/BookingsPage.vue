<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { Star } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { Schemas } from '@/shared/api/client'
import { dateTime, money } from '@/shared/format'

import Avatar from '../components/Avatar.vue'
import LoadState from '../components/LoadState.vue'
import PageHeader from '../components/PageHeader.vue'
import Sheet from '../components/Sheet.vue'
import { draft, resetDraft } from '../draft'
import { useBookings } from '../queries'
import { api, locale, refreshClient, session } from '../session'
import { haptic } from '../telegram'

const router = useRouter()
const queryClient = useQueryClient()
const bookings = useBookings()
const lang = computed(() => locale())
const business = computed(() => session.business!)
const tz = computed(() => business.value.timezone)

const tab = ref<'upcoming' | 'past'>('upcoming')
const selected = ref<Schemas['BookingOut'] | null>(null)
const open = ref(false)
const confirmCancel = ref(false)
const busy = ref(false)
const message = ref('')
const rating = ref(0)
const comment = ref('')

const active = (b: Schemas['BookingOut']) =>
  (b.status === 'confirmed' || b.status === 'pending_payment') && new Date(b.ends_at) > new Date()
const upcoming = computed(() =>
  (bookings.data.value ?? []).filter(active).sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
)
const past = computed(() => (bookings.data.value ?? []).filter((b) => !active(b)))
const list = computed(() => (tab.value === 'upcoming' ? upcoming.value : past.value))

const paidDeposit = computed(() => selected.value?.deposit_status === 'paid')

function fmt(cents: number): string {
  return money(cents, business.value.currency, lang.value)
}

function show(booking: Schemas['BookingOut']): void {
  haptic()
  selected.value = booking
  confirmCancel.value = false
  message.value = ''
  rating.value = booking.review?.rating ?? 0
  comment.value = booking.review?.comment ?? ''
  open.value = true
}

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ['bookings'] })
  void refreshClient()
}

async function cancel(): Promise<void> {
  if (!selected.value) return
  busy.value = true
  try {
    const result = await api.post<Schemas['CancelOut']>(
      `/api/app/bookings/${selected.value.id}/cancel`,
    )
    selected.value = result.booking
    message.value = result.refund === 'refunded' ? 'bookings.refunded' : 'bookings.cancelled'
    haptic('success')
    confirmCancel.value = false
    await refresh()
  } finally {
    busy.value = false
  }
}

function move(): void {
  if (!selected.value) return
  resetDraft()
  draft.serviceId = selected.value.service.id
  draft.masterId = selected.value.master.id
  draft.rescheduleId = selected.value.id
  open.value = false
  void router.push({ name: 'time' })
}

function pay(): void {
  if (!selected.value) return
  open.value = false
  void router.push({ name: 'pay', params: { id: selected.value.id } })
}

function rate(n: number): void {
  rating.value = n
  haptic()
}

async function sendReview(): Promise<void> {
  if (!selected.value || !rating.value) return
  busy.value = true
  try {
    selected.value = await api.post<Schemas['BookingOut']>(
      `/api/app/bookings/${selected.value.id}/review`,
      { rating: rating.value, comment: comment.value },
    )
    message.value = 'bookings.thanks'
    haptic('success')
    await refresh()
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main>
    <PageHeader :title="$t('nav.bookings')" />
    <div class="mx-4 mt-1 grid grid-cols-2 rounded-full bg-surface p-1" role="tablist">
      <button
        v-for="key in ['upcoming', 'past'] as const"
        :key="key"
        type="button"
        role="tab"
        :aria-selected="tab === key"
        class="rounded-full py-2 text-sm font-semibold transition-colors"
        :class="tab === key ? 'bg-ink text-bg' : 'text-muted'"
        @click="tab = key"
      >
        {{ $t(`bookings.${key}`) }}
        <span v-if="key === 'upcoming' && upcoming.length" class="num"
          >· {{ upcoming.length }}</span
        >
      </button>
    </div>

    <LoadState
      :loading="bookings.isPending.value"
      :error="bookings.isError.value"
      @retry="bookings.refetch()"
    />

    <div
      v-if="bookings.data.value && !list.length"
      class="mx-4 mt-6 rounded-[20px] bg-surface p-6 text-center"
    >
      <p class="text-muted">{{ $t('bookings.empty') }}</p>
      <RouterLink
        to="/"
        class="mt-4 inline-block rounded-full bg-accent px-5 py-2.5 font-semibold text-accent-ink"
      >
        {{ $t('bookings.emptyAction') }}
      </RouterLink>
    </div>

    <ul class="space-y-2 px-4 pt-4">
      <li v-for="booking in list" :key="booking.id">
        <button
          type="button"
          class="flex w-full items-center gap-3 rounded-[18px] bg-surface p-3 text-left transition-transform active:scale-[0.99]"
          @click="show(booking)"
        >
          <Avatar
            :src="booking.master.photo_url"
            :name="booking.master.name[lang]"
            :color="booking.master.color"
          />
          <span class="min-w-0 flex-1">
            <span class="block font-sign text-xl leading-tight font-semibold num">
              {{ dateTime(booking.starts_at, lang, tz) }}
            </span>
            <span class="block truncate text-sm text-muted">
              {{ booking.service.name[lang] }} · {{ booking.master.name[lang] }}
            </span>
          </span>
          <span
            class="rounded-full px-2 py-0.5 text-xs font-semibold"
            :class="{
              'bg-accent-soft text-accent':
                booking.status === 'confirmed' || booking.status === 'completed',
              'bg-brass-soft text-brass': booking.status === 'pending_payment',
              'bg-danger-soft text-danger':
                booking.status === 'cancelled' || booking.status === 'no_show',
            }"
          >
            {{ $t(`bookings.status.${booking.status}`) }}
          </span>
        </button>
      </li>
    </ul>

    <Sheet v-if="selected" v-model="open" :title="selected.service.name[lang]">
      <p class="mt-1 font-sign text-[26px] font-semibold num">
        {{ dateTime(selected.starts_at, lang, tz) }}
      </p>
      <p class="text-sm text-muted">{{ selected.master.name[lang] }} · {{ fmt(selected.price) }}</p>
      <ul class="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
        <li class="rounded-full bg-surface-2 px-2.5 py-1">
          {{ $t(`bookings.status.${selected.status}`) }}
        </li>
        <li
          v-if="selected.deposit && paidDeposit"
          class="rounded-full bg-accent-soft px-2.5 py-1 text-accent"
        >
          {{ $t('bookings.deposit', { amount: fmt(selected.deposit) }) }}
        </li>
        <li v-if="selected.bonus_spent" class="rounded-full bg-brass-soft px-2.5 py-1 text-brass">
          {{ $t('bookings.bonusUsed', { amount: fmt(selected.bonus_spent) }) }}
        </li>
      </ul>

      <p
        v-if="message"
        class="mt-4 rounded-xl bg-accent-soft p-3 text-sm font-semibold text-accent"
        role="status"
      >
        {{ $t(message) }}
      </p>

      <template v-if="selected.can_cancel">
        <p class="mt-4 text-sm text-muted">
          {{
            selected.can_reschedule
              ? $t('bookings.deadline', { deadline: dateTime(selected.refund_deadline, lang, tz) })
              : $t('bookings.deadlinePassed')
          }}
        </p>
        <div v-if="!confirmCancel" class="mt-4 grid gap-2">
          <button
            v-if="selected.status === 'pending_payment'"
            type="button"
            class="h-12 rounded-[14px] bg-accent font-semibold text-accent-ink"
            @click="pay"
          >
            {{ $t('bookings.pay') }}
          </button>
          <button
            v-if="selected.can_reschedule"
            type="button"
            class="h-12 rounded-[14px] bg-surface-2 font-semibold"
            @click="move"
          >
            {{ $t('bookings.move') }}
          </button>
          <button
            type="button"
            class="h-12 rounded-[14px] font-semibold text-danger"
            @click="confirmCancel = true"
          >
            {{ $t('bookings.cancel') }}
          </button>
        </div>
        <div v-else class="mt-4 rounded-[16px] bg-danger-soft p-4">
          <p class="text-sm">
            {{
              paidDeposit && !selected.can_reschedule
                ? $t('bookings.confirmCancelLate', {
                    hours: business.cancel_window_hours,
                    amount: fmt(selected.deposit),
                  })
                : $t('bookings.confirmCancel', { when: dateTime(selected.starts_at, lang, tz) })
            }}
          </p>
          <div class="mt-3 grid grid-cols-2 gap-2">
            <button
              type="button"
              class="h-11 rounded-[12px] bg-danger font-semibold text-white"
              :disabled="busy"
              @click="cancel"
            >
              {{ $t('bookings.yesCancel') }}
            </button>
            <button
              type="button"
              class="h-11 rounded-[12px] bg-surface font-semibold"
              @click="confirmCancel = false"
            >
              {{ $t('bookings.keep') }}
            </button>
          </div>
        </div>
      </template>

      <section v-if="selected.status === 'completed'" class="mt-5">
        <h3 class="font-semibold">
          {{ selected.review ? $t('bookings.rated') : $t('bookings.rate') }}
        </h3>
        <div class="mt-2 flex gap-1" role="radiogroup" :aria-label="$t('bookings.rate')">
          <button
            v-for="n in 5"
            :key="n"
            type="button"
            role="radio"
            :aria-checked="rating === n"
            :aria-label="String(n)"
            class="grid size-11 place-items-center rounded-full"
            @click="rate(n)"
          >
            <Star
              :size="28"
              :stroke-width="1.5"
              :class="n <= rating ? 'fill-brass text-brass' : 'text-line'"
            />
          </button>
        </div>
        <textarea
          v-model="comment"
          rows="2"
          maxlength="1000"
          :placeholder="$t('bookings.commentPlaceholder')"
          class="mt-2 w-full resize-none rounded-[14px] border border-line bg-surface-2 p-3 text-[15px] focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          class="mt-2 h-11 w-full rounded-[12px] bg-accent font-semibold text-accent-ink disabled:opacity-40"
          :disabled="!rating || busy"
          @click="sendReview"
        >
          {{ $t('bookings.send') }}
        </button>
      </section>
    </Sheet>
  </main>
</template>
