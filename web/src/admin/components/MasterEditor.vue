<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useClipboard } from '@vueuse/core'
import { Check, Copy, Link2, Trash2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { ApiError, type Schemas } from '@/shared/api/client'
import { dateTime } from '@/shared/format'
import { addDays, todayIn, zonedToIso } from '@/shared/zone'

import { api } from '../api'
import { useServices, useShop } from '../context'
import MasterAvatar from './MasterAvatar.vue'

const props = defineProps<{ item: Schemas['AdminMasterOut'] }>()
const queryClient = useQueryClient()
const { lang, tz, fmt } = useShop()
const services = useServices()
const { copy, copied } = useClipboard()

interface Row {
  works: boolean
  start: string
  end: string
  lunch: boolean
  lunchStart: string
  lunchEnd: string
}

const rows = ref<Row[]>([])
const prices = ref<Record<number, { enabled: boolean; price: number | null }>>({})
const saved = ref<'schedule' | 'services' | null>(null)
const error = ref('')

watch(
  () => props.item,
  (item) => {
    rows.value = Array.from({ length: 7 }, (_, weekday) => {
      const work = item.hours.find((h) => h.weekday === weekday)
      const lunch = item.breaks.find((b) => b.weekday === weekday)
      return {
        works: !!work,
        start: work?.start.slice(0, 5) ?? '10:00',
        end: work?.end.slice(0, 5) ?? '19:00',
        lunch: !!lunch,
        lunchStart: lunch?.start.slice(0, 5) ?? '14:00',
        lunchEnd: lunch?.end.slice(0, 5) ?? '14:45',
      }
    })
  },
  { immediate: true },
)

watch(
  () => [props.item, services.data.value] as const,
  ([item, list]) => {
    prices.value = Object.fromEntries(
      (list ?? []).map((s) => {
        const link = item.services.find((l) => l.service_id === s.id)
        return [s.id, { enabled: !!link, price: link?.price != null ? link.price / 100 : null }]
      }),
    )
  },
  { immediate: true },
)

// 2024-01-01 was a Monday; Intl gives localized short weekday names.
const weekdays = computed(() =>
  Array.from({ length: 7 }, (_, i) =>
    new Intl.DateTimeFormat(lang.value, { weekday: 'short', timeZone: 'UTC' }).format(
      new Date(Date.UTC(2024, 0, 1 + i)),
    ),
  ),
)

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ['admin', 'masters'] })
  await queryClient.invalidateQueries({ queryKey: ['admin', 'journal'] })
}

function flash(kind: 'schedule' | 'services'): void {
  saved.value = kind
  setTimeout(() => (saved.value = null), 1800)
}

const saveSchedule = useMutation({
  mutationFn: () =>
    api.put(`/api/admin/masters/${props.item.master.id}/schedule`, {
      hours: rows.value.flatMap((r, weekday) =>
        r.works ? [{ weekday, start: r.start, end: r.end }] : [],
      ),
      breaks: rows.value.flatMap((r, weekday) =>
        r.works && r.lunch ? [{ weekday, start: r.lunchStart, end: r.lunchEnd }] : [],
      ),
    }),
  onSuccess: async () => {
    error.value = ''
    flash('schedule')
    await refresh()
  },
  onError: (e) => (error.value = e.message),
})

const saveServices = useMutation({
  mutationFn: () =>
    api.put(`/api/admin/masters/${props.item.master.id}/services`, {
      services: Object.entries(prices.value)
        .filter(([, v]) => v.enabled)
        .map(([id, v]) => ({
          service_id: Number(id),
          price: v.price === null || Number.isNaN(v.price) ? null : Math.round(v.price * 100),
          duration_minutes: null,
        })),
    }),
  onSuccess: async () => {
    flash('services')
    await refresh()
  },
})

const newLink = useMutation({
  mutationFn: () => api.post(`/api/admin/masters/${props.item.master.id}/link`),
  onSuccess: refresh,
})

const offs = useQuery({
  queryKey: ['admin', 'time-off', () => props.item.master.id],
  queryFn: () =>
    api.get<Schemas['TimeOffOut'][]>(`/api/admin/masters/${props.item.master.id}/time-off`),
})
const offFrom = ref('')
const offTo = ref('')
const offReason = ref('')
watch(
  tz,
  (zone) => {
    offFrom.value = addDays(todayIn(zone), 7)
    offTo.value = addDays(todayIn(zone), 8)
  },
  { immediate: true },
)

const addOff = useMutation({
  mutationFn: () =>
    api.post(`/api/admin/masters/${props.item.master.id}/time-off`, {
      starts_at: zonedToIso(offFrom.value, '00:00', tz.value),
      ends_at: zonedToIso(offTo.value, '00:00', tz.value),
      reason: offReason.value,
    }),
  onSuccess: async () => {
    offReason.value = ''
    error.value = ''
    await offs.refetch()
    await refresh()
  },
  onError: (e) => (error.value = e instanceof ApiError ? e.message : String(e)),
})

const removeOff = useMutation({
  mutationFn: (id: number) => api.del(`/api/admin/time-off/${id}`),
  onSuccess: async () => {
    await offs.refetch()
    await refresh()
  },
})
</script>

<template>
  <article class="rounded-2xl border border-line bg-surface">
    <header class="flex flex-wrap items-center gap-3 border-b border-line p-4">
      <MasterAvatar :master="item.master" :lang="lang" :size="48" />
      <div class="mr-auto">
        <h2 class="font-sign text-2xl leading-tight font-semibold">{{ item.master.name[lang] }}</h2>
        <p class="text-sm text-muted">{{ item.master.title[lang] }}</p>
      </div>
      <div class="text-right text-sm">
        <p class="font-semibold">{{ $t('masters.telegram') }}</p>
        <p :class="item.telegram_linked ? 'text-accent' : 'text-muted'">
          {{ item.telegram_linked ? $t('masters.linked') : $t('masters.notLinked') }}
        </p>
      </div>
    </header>

    <div class="grid gap-6 p-4 xl:grid-cols-2">
      <section>
        <h3 class="font-semibold">{{ $t('masters.schedule') }}</h3>
        <table class="mt-2 w-full text-sm">
          <tbody>
            <tr
              v-for="(row, weekday) in rows"
              :key="weekday"
              class="border-b border-line last:border-b-0"
            >
              <td class="w-14 py-1.5">
                <label class="flex items-center gap-2 font-semibold">
                  <input
                    v-model="row.works"
                    type="checkbox"
                    class="size-4 accent-[var(--accent)]"
                  />
                  {{ weekdays[weekday] }}
                </label>
              </td>
              <td class="py-1.5">
                <div v-if="row.works" class="flex flex-wrap items-center gap-1.5">
                  <input
                    v-model="row.start"
                    type="time"
                    step="900"
                    class="h-8 rounded-md border border-line bg-surface px-1.5"
                    :aria-label="$t('masters.from')"
                  />
                  <span class="text-muted">–</span>
                  <input
                    v-model="row.end"
                    type="time"
                    step="900"
                    class="h-8 rounded-md border border-line bg-surface px-1.5"
                    :aria-label="$t('masters.to')"
                  />
                  <label class="ml-2 flex items-center gap-1 text-xs text-muted">
                    <input
                      v-model="row.lunch"
                      type="checkbox"
                      class="size-3.5 accent-[var(--accent)]"
                    />
                    {{ $t('masters.lunch') }}
                  </label>
                  <template v-if="row.lunch">
                    <input
                      v-model="row.lunchStart"
                      type="time"
                      step="900"
                      class="h-8 rounded-md border border-line bg-surface px-1.5"
                    />
                    <input
                      v-model="row.lunchEnd"
                      type="time"
                      step="900"
                      class="h-8 rounded-md border border-line bg-surface px-1.5"
                    />
                  </template>
                </div>
                <span v-else class="text-muted">{{ $t('journal.dayOff') }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <button
          type="button"
          class="mt-3 flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-semibold text-accent-ink"
          @click="saveSchedule.mutate()"
        >
          <Check v-if="saved === 'schedule'" :size="16" />
          {{ saved === 'schedule' ? $t('common.saved') : $t('common.save') }}
        </button>
      </section>

      <section>
        <h3 class="font-semibold">{{ $t('masters.services') }}</h3>
        <ul class="mt-2 max-h-[300px] space-y-1 overflow-y-auto pr-1 text-sm">
          <li v-for="s in services.data.value ?? []" :key="s.id" class="flex items-center gap-2">
            <label class="flex min-w-0 flex-1 items-center gap-2">
              <input
                v-model="prices[s.id]!.enabled"
                type="checkbox"
                class="size-4 accent-[var(--accent)]"
              />
              <span class="truncate">{{ s.name[lang] }}</span>
              <span class="shrink-0 text-xs text-faint">{{
                $t('masters.basePrice', { price: fmt(s.price) })
              }}</span>
            </label>
            <input
              v-if="prices[s.id]?.enabled"
              v-model.number="prices[s.id]!.price"
              type="number"
              min="0"
              step="1"
              :placeholder="String(s.price / 100)"
              :aria-label="$t('masters.ownPrice')"
              class="h-8 w-20 rounded-md border border-line bg-surface px-2 text-right"
            />
          </li>
        </ul>
        <button
          type="button"
          class="mt-3 flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-semibold text-accent-ink"
          @click="saveServices.mutate()"
        >
          <Check v-if="saved === 'services'" :size="16" />
          {{ saved === 'services' ? $t('common.saved') : $t('common.save') }}
        </button>
      </section>

      <section>
        <h3 class="font-semibold">{{ $t('masters.timeOff') }}</h3>
        <ul class="mt-2 space-y-1 text-sm">
          <li
            v-for="off in offs.data.value ?? []"
            :key="off.id"
            class="flex items-center justify-between gap-2 rounded-lg bg-surface-2 px-3 py-2"
          >
            <span
              >{{ dateTime(off.starts_at, lang, tz) }} — {{ dateTime(off.ends_at, lang, tz)
              }}<template v-if="off.reason"> · {{ off.reason }}</template></span
            >
            <button
              type="button"
              class="text-muted hover:text-danger"
              :aria-label="$t('booking.cancel')"
              @click="removeOff.mutate(off.id)"
            >
              <Trash2 :size="16" />
            </button>
          </li>
        </ul>
        <form class="mt-2 flex flex-wrap items-end gap-2 text-sm" @submit.prevent="addOff.mutate()">
          <input
            v-model="offFrom"
            type="date"
            required
            class="h-9 rounded-md border border-line bg-surface px-2"
          />
          <input
            v-model="offTo"
            type="date"
            required
            class="h-9 rounded-md border border-line bg-surface px-2"
          />
          <input
            v-model="offReason"
            :placeholder="$t('masters.reason')"
            class="h-9 min-w-0 flex-1 rounded-md border border-line bg-surface px-2"
          />
          <button
            type="submit"
            class="h-9 rounded-md border border-line px-3 font-semibold hover:bg-surface-2"
          >
            {{ $t('masters.addTimeOff') }}
          </button>
        </form>
      </section>

      <section>
        <h3 class="font-semibold">{{ $t('masters.telegram') }}</h3>
        <p v-if="!item.link_url" class="mt-2 text-sm text-muted">{{ $t('masters.linkHidden') }}</p>
        <div v-else class="mt-2 flex items-center gap-2">
          <code class="min-w-0 flex-1 truncate rounded-md bg-surface-2 px-2 py-2 text-xs">{{
            item.link_url
          }}</code>
          <button
            type="button"
            class="flex h-9 items-center gap-1.5 rounded-md border border-line px-3 text-sm font-semibold"
            @click="copy(item.link_url)"
          >
            <Copy :size="14" /> {{ copied ? $t('common.saved') : $t('masters.copyLink') }}
          </button>
        </div>
        <button
          type="button"
          class="mt-2 flex h-9 items-center gap-1.5 rounded-md border border-line px-3 text-sm font-semibold hover:bg-surface-2"
          @click="newLink.mutate()"
        >
          <Link2 :size="14" /> {{ $t('masters.newLink') }}
        </button>
      </section>
    </div>
    <p
      v-if="error"
      class="mx-4 mb-4 rounded-lg bg-danger-soft p-3 text-sm text-danger"
      role="alert"
    >
      {{ error }}
    </p>
  </article>
</template>
