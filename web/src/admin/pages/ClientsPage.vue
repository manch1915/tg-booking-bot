<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { refDebounced } from '@vueuse/core'
import { ChevronLeft, ChevronRight, Search, Send } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { dateTime, day } from '@/shared/format'

import { api } from '../api'
import SidePanel from '../components/SidePanel.vue'
import { useShop } from '../context'

const PER_PAGE = 30
const SEGMENTS = ['all', 'inactive_30', 'new_clients', 'with_bonuses'] as const

const queryClient = useQueryClient()
const { lang, tz, fmt } = useShop()
const q = ref('')
const query = refDebounced(q, 300)
const segment = ref<(typeof SEGMENTS)[number]>('all')
const page = ref(1)
watch([query, segment], () => (page.value = 1))

const clients = useQuery({
  queryKey: ['admin', 'clients', query, segment, page],
  queryFn: () =>
    api.get<Schemas['ClientsPage']>('/api/admin/clients', {
      q: query.value,
      segment: segment.value,
      page: page.value,
      per_page: PER_PAGE,
    }),
  placeholderData: (previous) => previous,
})
const pages = computed(() => Math.max(1, Math.ceil((clients.data.value?.total ?? 0) / PER_PAGE)))

const selectedId = ref<number | null>(null)
const open = ref(false)
const detail = useQuery({
  queryKey: ['admin', 'client', selectedId],
  queryFn: () => api.get<Schemas['ClientDetail']>(`/api/admin/clients/${selectedId.value}`),
  enabled: computed(() => selectedId.value !== null),
})
const amount = ref<number | null>(null)
const reason = ref('')
const notes = ref('')
watch(
  () => detail.data.value,
  (d) => (notes.value = d?.notes ?? ''),
)

function show(id: number): void {
  selectedId.value = id
  open.value = true
  amount.value = null
  reason.value = ''
}

async function afterChange(data: Schemas['ClientDetail']): Promise<void> {
  queryClient.setQueryData(['admin', 'client', selectedId], data)
  await queryClient.invalidateQueries({ queryKey: ['admin', 'clients'] })
}

const adjust = useMutation({
  mutationFn: () =>
    api.post<Schemas['ClientDetail']>(`/api/admin/clients/${selectedId.value}/bonus`, {
      amount: Math.round((amount.value ?? 0) * 100),
      comment: reason.value,
    }),
  onSuccess: async (data) => {
    amount.value = null
    reason.value = ''
    await afterChange(data)
    void detail.refetch()
  },
})

const saveNotes = useMutation({
  mutationFn: () =>
    api.patch<Schemas['ClientDetail']>(`/api/admin/clients/${selectedId.value}`, {
      notes: notes.value,
    }),
  onSuccess: afterChange,
})
</script>

<template>
  <main class="space-y-4 p-4 lg:p-6">
    <header class="flex flex-wrap items-center gap-3">
      <h1 class="mr-auto font-sign text-3xl font-semibold">{{ $t('nav.clients') }}</h1>
      <label class="relative block w-full sm:w-72">
        <span class="sr-only">{{ $t('common.search') }}</span>
        <Search :size="16" class="absolute top-1/2 left-3 -translate-y-1/2 text-faint" />
        <input
          v-model="q"
          type="search"
          :placeholder="$t('common.search')"
          class="h-10 w-full rounded-lg border border-line bg-surface pr-3 pl-9 focus:border-accent focus:outline-none"
        />
      </label>
    </header>

    <div class="flex flex-wrap gap-2" role="radiogroup">
      <button
        v-for="key in SEGMENTS"
        :key="key"
        type="button"
        role="radio"
        :aria-checked="segment === key"
        class="rounded-full px-3 py-1.5 text-sm font-semibold"
        :class="segment === key ? 'bg-ink text-bg' : 'bg-surface text-muted'"
        @click="segment = key"
      >
        {{ $t(`clients.segment.${key}`) }}
      </button>
      <span class="ml-auto self-center text-sm text-muted">
        {{ $t('clients.total', { n: clients.data.value?.total ?? 0 }) }}
      </span>
    </div>

    <div class="overflow-x-auto rounded-2xl border border-line bg-surface">
      <table class="w-full min-w-[720px] text-sm">
        <thead class="text-left text-xs text-muted">
          <tr class="border-b border-line">
            <th class="px-4 py-3 font-semibold">{{ $t('booking.client') }}</th>
            <th class="px-4 py-3 text-right font-semibold">{{ $t('clients.visits') }}</th>
            <th class="px-4 py-3 font-semibold">{{ $t('clients.lastVisit') }}</th>
            <th class="px-4 py-3 text-right font-semibold">{{ $t('clients.spent') }}</th>
            <th class="px-4 py-3 text-right font-semibold">{{ $t('clients.bonus') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in clients.data.value?.items ?? []"
            :key="c.id"
            class="cursor-pointer border-b border-line last:border-b-0 hover:bg-surface-2"
            tabindex="0"
            @click="show(c.id)"
            @keydown.enter="show(c.id)"
          >
            <td class="px-4 py-2.5">
              <span class="flex items-center gap-2 font-semibold">
                {{ c.name }}
                <Send
                  v-if="c.in_telegram"
                  :size="13"
                  class="text-accent"
                  :aria-label="$t('clients.telegram')"
                />
              </span>
              <span class="text-xs text-muted">{{ c.phone ?? '—' }}</span>
            </td>
            <td class="px-4 py-2.5 text-right num">{{ c.visits }}</td>
            <td class="px-4 py-2.5 text-muted">
              {{ c.last_visit ? day(c.last_visit, lang, tz) : '—' }}
            </td>
            <td class="px-4 py-2.5 text-right num">{{ fmt(c.spent) }}</td>
            <td class="px-4 py-2.5 text-right text-brass num">{{ fmt(c.bonus_balance) }}</td>
          </tr>
        </tbody>
      </table>
      <p
        v-if="clients.data.value && !clients.data.value.items.length"
        class="p-6 text-center text-muted"
      >
        {{ $t('common.noData') }}
      </p>
    </div>

    <nav class="flex items-center justify-end gap-2" aria-label="Pagination">
      <button
        type="button"
        class="grid size-9 place-items-center rounded-lg border border-line bg-surface disabled:opacity-40"
        :disabled="page <= 1"
        aria-label="Previous page"
        @click="page--"
      >
        <ChevronLeft :size="16" />
      </button>
      <span class="text-sm text-muted num">{{ page }} / {{ pages }}</span>
      <button
        type="button"
        class="grid size-9 place-items-center rounded-lg border border-line bg-surface disabled:opacity-40"
        :disabled="page >= pages"
        aria-label="Next page"
        @click="page++"
      >
        <ChevronRight :size="16" />
      </button>
    </nav>

    <SidePanel
      v-if="detail.data.value"
      v-model="open"
      :title="detail.data.value.client.name"
      :subtitle="detail.data.value.client.phone ?? undefined"
    >
      <div class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-xl bg-surface-2 p-3">
          <p class="font-sign text-2xl font-semibold num">{{ detail.data.value.client.visits }}</p>
          <p class="text-xs text-muted">{{ $t('clients.visits') }}</p>
        </div>
        <div class="rounded-xl bg-surface-2 p-3">
          <p class="font-sign text-2xl font-semibold num">
            {{ fmt(detail.data.value.client.spent) }}
          </p>
          <p class="text-xs text-muted">{{ $t('clients.spent') }}</p>
        </div>
        <div class="rounded-xl bg-brass-soft p-3">
          <p class="font-sign text-2xl font-semibold text-brass num">
            {{ fmt(detail.data.value.client.bonus_balance) }}
          </p>
          <p class="text-xs text-muted">{{ $t('clients.bonus') }}</p>
        </div>
      </div>

      <form class="mt-5 rounded-xl border border-line p-3" @submit.prevent="adjust.mutate()">
        <p class="text-sm font-semibold">{{ $t('clients.adjust') }}</p>
        <div class="mt-2 flex gap-2">
          <input
            v-model.number="amount"
            type="number"
            step="0.5"
            required
            :placeholder="$t('clients.amount')"
            class="h-10 w-28 rounded-lg border border-line bg-surface px-2"
          />
          <input
            v-model="reason"
            :placeholder="$t('clients.reason')"
            maxlength="200"
            class="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-2"
          />
          <button
            type="submit"
            class="h-10 rounded-lg bg-accent px-3 text-sm font-semibold text-accent-ink"
            :disabled="adjust.isPending.value"
          >
            {{ $t('clients.apply') }}
          </button>
        </div>
        <p v-if="adjust.isError.value" class="mt-2 text-sm text-danger">
          {{ adjust.error.value?.message }}
        </p>
      </form>

      <label class="mt-5 block">
        <span class="text-sm font-semibold">{{ $t('clients.notes') }}</span>
        <textarea
          v-model="notes"
          rows="2"
          maxlength="2000"
          class="mt-1 w-full resize-none rounded-lg border border-line bg-surface p-2.5"
          @blur="saveNotes.mutate()"
        />
      </label>

      <h3 class="mt-5 text-sm font-semibold">{{ $t('clients.history') }}</h3>
      <ul class="mt-2 divide-y divide-line rounded-xl border border-line text-sm">
        <li
          v-for="b in detail.data.value.bookings"
          :key="b.id"
          class="flex items-center gap-3 px-3 py-2"
        >
          <span class="h-8 w-1 rounded-full" :style="{ background: b.master.color }" />
          <span class="min-w-0 flex-1">
            <span class="block truncate font-semibold">{{ b.service.name[lang] }}</span>
            <span class="text-xs text-muted"
              >{{ dateTime(b.starts_at, lang, tz) }} · {{ b.master.name[lang] }}</span
            >
          </span>
          <span class="text-right">
            <span class="block num">{{ fmt(b.price) }}</span>
            <span class="text-xs text-muted">{{ $t(`status.${b.status}`) }}</span>
          </span>
        </li>
      </ul>

      <h3 class="mt-5 text-sm font-semibold">{{ $t('clients.bonusHistory') }}</h3>
      <ul class="mt-2 space-y-1 text-sm">
        <li
          v-for="(tx, i) in detail.data.value.bonuses"
          :key="i"
          class="flex justify-between gap-3"
        >
          <span class="text-muted"
            >{{ day(tx.created_at, lang, tz) }} · {{ tx.kind
            }}<template v-if="tx.comment"> · {{ tx.comment }}</template></span
          >
          <span class="num" :class="tx.amount > 0 ? 'text-accent' : 'text-muted'"
            >{{ tx.amount > 0 ? '+' : '' }}{{ fmt(tx.amount) }}</span
          >
        </li>
      </ul>
    </SidePanel>
  </main>
</template>
