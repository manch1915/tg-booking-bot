<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { Check, MessageSquare, Phone, Send, UserX, X } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { ApiError, type Schemas } from '@/shared/api/client'
import { dateTime } from '@/shared/format'
import { minutesOfDay, hhmm, zonedToIso } from '@/shared/zone'

import { api } from '../api'
import { useMasters, useShop } from '../context'
import SidePanel from './SidePanel.vue'

const open = defineModel<boolean>({ required: true })
const props = defineProps<{ booking: Schemas['AdminBookingOut'] | null }>()

const queryClient = useQueryClient()
const { lang, tz, fmt } = useShop()
const masters = useMasters()
const current = ref<Schemas['AdminBookingOut'] | null>(props.booking)
const mode = ref<'view' | 'cancel' | 'move'>('view')
const reason = ref('')
const moveDate = ref('')
const moveTime = ref('')
const moveMaster = ref<number | null>(null)
const error = ref('')

watch(
  () => props.booking,
  (b) => {
    current.value = b
    mode.value = 'view'
    error.value = ''
    reason.value = ''
    if (b) {
      moveDate.value = new Intl.DateTimeFormat('en-CA', { timeZone: tz.value }).format(
        new Date(b.starts_at),
      )
      moveTime.value = hhmm(minutesOfDay(b.starts_at, tz.value))
      moveMaster.value = b.master.id
    }
  },
  { immediate: true },
)

const active = computed(
  () => current.value?.status === 'confirmed' || current.value?.status === 'pending_payment',
)
const started = computed(() => !!current.value && new Date(current.value.starts_at) < new Date())

async function refresh(updated: Schemas['AdminBookingOut']): Promise<void> {
  current.value = updated
  mode.value = 'view'
  await queryClient.invalidateQueries({ queryKey: ['admin', 'journal'] })
}

const status = useMutation({
  mutationFn: (body: { action: string; reason?: string }) =>
    api.post<Schemas['AdminBookingOut']>(`/api/admin/bookings/${current.value!.id}/status`, body),
  onSuccess: refresh,
  onError: (e) => (error.value = e.message),
})

const move = useMutation({
  mutationFn: () =>
    api.post<Schemas['AdminBookingOut']>(`/api/admin/bookings/${current.value!.id}/reschedule`, {
      starts_at: zonedToIso(moveDate.value, moveTime.value, tz.value),
      master_id: moveMaster.value,
    }),
  onSuccess: refresh,
  onError: (e) =>
    (error.value = e instanceof ApiError && e.status === 409 ? 'booking.busy' : e.message),
})
</script>

<template>
  <SidePanel
    v-if="current"
    v-model="open"
    :title="current.client.name"
    :subtitle="dateTime(current.starts_at, lang, tz)"
  >
    <div class="flex flex-wrap gap-2 text-xs font-semibold">
      <span class="rounded-full bg-surface-2 px-2.5 py-1">{{
        $t(`status.${current.status}`)
      }}</span>
      <span class="rounded-full bg-surface-2 px-2.5 py-1">{{
        $t(`source.${current.source}`)
      }}</span>
      <span class="rounded-full bg-surface-2 px-2.5 py-1">{{
        $t(`method.${current.payment_method}`)
      }}</span>
    </div>

    <dl class="mt-5 grid grid-cols-[120px_1fr] gap-y-2.5 text-sm">
      <dt class="text-muted">{{ $t('booking.service') }}</dt>
      <dd class="font-semibold">{{ current.service.name[lang] }}</dd>
      <dt class="text-muted">{{ $t('booking.master') }}</dt>
      <dd class="flex items-center gap-2">
        <span class="size-2.5 rounded-full" :style="{ background: current.master.color }" />
        {{ current.master.name[lang] }}
      </dd>
      <dt class="text-muted">{{ $t('booking.price') }}</dt>
      <dd class="num">{{ fmt(current.price) }}</dd>
      <template v-if="current.bonus_spent">
        <dt class="text-muted">{{ $t('booking.bonus') }}</dt>
        <dd class="text-brass num">−{{ fmt(current.bonus_spent) }}</dd>
      </template>
      <template v-if="current.deposit">
        <dt class="text-muted">{{ $t('booking.deposit') }}</dt>
        <dd class="num">{{ fmt(current.deposit) }} · {{ current.deposit_status ?? '—' }}</dd>
      </template>
      <dt class="text-muted">{{ $t('booking.client') }}</dt>
      <dd class="flex flex-wrap items-center gap-3">
        <a
          v-if="current.client.phone"
          :href="`tel:${current.client.phone}`"
          class="inline-flex items-center gap-1 text-accent"
        >
          <Phone :size="14" /> {{ current.client.phone }}
        </a>
        <span v-if="current.client.in_telegram" class="inline-flex items-center gap-1 text-muted">
          <Send :size="14" /> Telegram
        </span>
      </dd>
      <template v-if="current.comment">
        <dt class="text-muted">{{ $t('booking.comment') }}</dt>
        <dd class="flex gap-1.5">
          <MessageSquare :size="14" class="mt-0.5 shrink-0 text-muted" />{{ current.comment }}
        </dd>
      </template>
      <template v-if="current.review">
        <dt class="text-muted">{{ $t('booking.review') }}</dt>
        <dd>
          <span class="text-brass">{{ '★'.repeat(current.review.rating) }}</span>
          <span v-if="current.review.comment" class="block text-muted">{{
            current.review.comment
          }}</span>
        </dd>
      </template>
      <template v-if="current.cancel_reason && current.status === 'cancelled'">
        <dt class="text-muted">{{ $t('booking.cancelReason') }}</dt>
        <dd>{{ current.cancel_reason }}</dd>
      </template>
    </dl>

    <section v-if="current.payments.length" class="mt-5">
      <h3 class="text-sm font-semibold">{{ $t('booking.payments') }}</h3>
      <ul class="mt-2 divide-y divide-line rounded-xl border border-line text-sm">
        <li v-for="p in current.payments" :key="p.id" class="flex justify-between px-3 py-2">
          <span>{{ p.purpose }} · {{ p.provider }}</span>
          <span class="num"
            >{{ p.currency === 'XTR' ? `${p.amount} ★` : fmt(p.amount) }} · {{ p.status }}</span
          >
        </li>
      </ul>
    </section>

    <section v-if="mode === 'move'" class="mt-5 space-y-3 rounded-xl border border-line p-4">
      <h3 class="font-semibold">{{ $t('booking.moveTo') }}</h3>
      <div class="grid grid-cols-2 gap-2">
        <input
          v-model="moveDate"
          type="date"
          class="h-10 rounded-lg border border-line bg-surface px-2"
        />
        <input
          v-model="moveTime"
          type="time"
          step="300"
          class="h-10 rounded-lg border border-line bg-surface px-2"
        />
      </div>
      <select
        v-model="moveMaster"
        class="h-10 w-full rounded-lg border border-line bg-surface px-2"
      >
        <option v-for="m in masters.data.value ?? []" :key="m.master.id" :value="m.master.id">
          {{ m.master.name[lang] }}
        </option>
      </select>
      <button
        type="button"
        class="h-10 w-full rounded-lg bg-accent font-semibold text-accent-ink"
        :disabled="move.isPending.value"
        @click="move.mutate()"
      >
        {{ $t('common.save') }}
      </button>
    </section>

    <section v-if="mode === 'cancel'" class="mt-5 space-y-3 rounded-xl bg-danger-soft p-4">
      <p class="text-sm">{{ $t('booking.cancelConfirm') }}</p>
      <input
        v-model="reason"
        :placeholder="$t('booking.cancelReason')"
        class="h-10 w-full rounded-lg border border-line bg-surface px-3"
      />
      <button
        type="button"
        class="h-10 w-full rounded-lg bg-danger font-semibold text-white"
        :disabled="status.isPending.value"
        @click="status.mutate({ action: 'cancel', reason })"
      >
        {{ $t('booking.cancel') }}
      </button>
    </section>

    <p v-if="error" class="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger" role="alert">
      {{ error.includes('.') ? $t(error) : error }}
    </p>

    <template v-if="active" #footer>
      <div class="grid grid-cols-2 gap-2">
        <button
          v-if="current.status === 'confirmed' && started"
          type="button"
          class="flex h-10 items-center justify-center gap-1.5 rounded-lg bg-accent font-semibold text-accent-ink"
          @click="status.mutate({ action: 'complete' })"
        >
          <Check :size="16" /> {{ $t('booking.complete') }}
        </button>
        <button
          v-if="current.status === 'confirmed' && started"
          type="button"
          class="flex h-10 items-center justify-center gap-1.5 rounded-lg border border-line font-semibold"
          @click="status.mutate({ action: 'no_show' })"
        >
          <UserX :size="16" /> {{ $t('booking.noShow') }}
        </button>
        <button
          v-if="current.status === 'confirmed' && !started"
          type="button"
          class="h-10 rounded-lg border border-line font-semibold"
          @click="mode = mode === 'move' ? 'view' : 'move'"
        >
          {{ $t('booking.move') }}
        </button>
        <button
          v-if="!started"
          type="button"
          class="flex h-10 items-center justify-center gap-1.5 rounded-lg font-semibold text-danger hover:bg-danger-soft"
          @click="mode = mode === 'cancel' ? 'view' : 'cancel'"
        >
          <X :size="16" /> {{ $t('booking.cancel') }}
        </button>
      </div>
    </template>
  </SidePanel>
</template>
