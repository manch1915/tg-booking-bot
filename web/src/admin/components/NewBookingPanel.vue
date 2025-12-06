<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'

import { ApiError, type Schemas } from '@/shared/api/client'
import { hhmm, zonedToIso } from '@/shared/zone'

import { api } from '../api'
import { useMasters, useServices, useShop } from '../context'
import SidePanel from './SidePanel.vue'

const open = defineModel<boolean>({ required: true })
const props = defineProps<{ day: string; masterId: number | null; minutes: number | null }>()
const emit = defineEmits<{ created: [booking: Schemas['AdminBookingOut']] }>()

const queryClient = useQueryClient()
const { lang, tz, fmt } = useShop()
const masters = useMasters()
const services = useServices()

const form = ref({
  name: '',
  phone: '',
  serviceId: null as number | null,
  masterId: null as number | null,
  date: props.day,
  time: '12:00',
  comment: '',
})
const error = ref('')

watch(
  () => [open.value, props.day, props.masterId, props.minutes] as const,
  ([isOpen]) => {
    if (!isOpen) return
    form.value.date = props.day
    form.value.masterId = props.masterId
    form.value.time = props.minutes !== null ? hhmm(props.minutes) : '12:00'
    error.value = ''
  },
  { immediate: true },
)

const offered = computed(() => {
  const master = masters.data.value?.find((m) => m.master.id === form.value.masterId)
  const ids = new Set(master?.services.map((s) => s.service_id))
  return (services.data.value ?? []).filter((s) => s.is_active && (!master || ids.has(s.id)))
})

const create = useMutation({
  mutationFn: () =>
    api.post<Schemas['AdminBookingOut']>('/api/admin/bookings', {
      client_name: form.value.name,
      client_phone: form.value.phone,
      service_id: form.value.serviceId,
      master_id: form.value.masterId,
      starts_at: zonedToIso(form.value.date, form.value.time, tz.value),
      comment: form.value.comment,
    }),
  onSuccess: async (booking) => {
    await queryClient.invalidateQueries({ queryKey: ['admin', 'journal'] })
    emit('created', booking)
    open.value = false
    form.value = { ...form.value, name: '', phone: '', comment: '', serviceId: null }
  },
  onError: (e) => {
    error.value = e instanceof ApiError && e.status === 409 ? 'booking.busy' : e.message
  },
})
</script>

<template>
  <SidePanel v-model="open" :title="$t('booking.newTitle')">
    <form id="new-booking" class="space-y-4" @submit.prevent="create.mutate()">
      <div class="grid grid-cols-2 gap-3">
        <label class="col-span-2 block sm:col-span-1">
          <span class="text-sm font-semibold">{{ $t('booking.clientName') }}</span>
          <input
            v-model="form.name"
            required
            maxlength="120"
            class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
          />
        </label>
        <label class="col-span-2 block sm:col-span-1">
          <span class="text-sm font-semibold">{{ $t('booking.clientPhone') }}</span>
          <input
            v-model="form.phone"
            type="tel"
            maxlength="32"
            placeholder="+374"
            class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
          />
        </label>
      </div>
      <label class="block">
        <span class="text-sm font-semibold">{{ $t('booking.master') }}</span>
        <select
          v-model="form.masterId"
          required
          class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-2"
        >
          <option v-for="m in masters.data.value ?? []" :key="m.master.id" :value="m.master.id">
            {{ m.master.name[lang] }}
          </option>
        </select>
      </label>
      <label class="block">
        <span class="text-sm font-semibold">{{ $t('booking.service') }}</span>
        <select
          v-model="form.serviceId"
          required
          class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-2"
        >
          <option v-for="s in offered" :key="s.id" :value="s.id">
            {{ s.name[lang] }} · {{ s.duration_minutes }} · {{ fmt(s.price) }}
          </option>
        </select>
      </label>
      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('booking.when') }}</span>
          <input
            v-model="form.date"
            type="date"
            required
            class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-2"
          />
        </label>
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('booking.startsAt') }}</span>
          <input
            v-model="form.time"
            type="time"
            step="300"
            required
            class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-2"
          />
        </label>
      </div>
      <label class="block">
        <span class="text-sm font-semibold">{{ $t('booking.comment') }}</span>
        <textarea
          v-model="form.comment"
          rows="2"
          maxlength="500"
          class="mt-1 w-full resize-none rounded-lg border border-line bg-surface p-3"
        />
      </label>
      <p v-if="error" class="rounded-lg bg-danger-soft p-3 text-sm text-danger" role="alert">
        {{ error.includes('.') ? $t(error) : error }}
      </p>
    </form>
    <template #footer>
      <button
        type="submit"
        form="new-booking"
        class="h-11 w-full rounded-lg bg-accent font-semibold text-accent-ink disabled:opacity-60"
        :disabled="create.isPending.value"
      >
        {{ $t('booking.create') }}
      </button>
    </template>
  </SidePanel>
</template>
