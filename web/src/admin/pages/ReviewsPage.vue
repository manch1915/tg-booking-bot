<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'

import type { Schemas } from '@/shared/api/client'
import { day, dateTime } from '@/shared/format'

import { api } from '../api'
import MasterAvatar from '../components/MasterAvatar.vue'
import { useMasters, useShop } from '../context'

const { lang, tz } = useShop()
const masters = useMasters()
const reviews = useQuery({
  queryKey: ['admin', 'reviews'],
  queryFn: () => api.get<Schemas['ReviewRow'][]>('/api/admin/reviews'),
})
const waitlist = useQuery({
  queryKey: ['admin', 'waitlist'],
  queryFn: () => api.get<Schemas['WaitlistRow'][]>('/api/admin/waitlist'),
})

const master = (id: number | null) => masters.data.value?.find((m) => m.master.id === id)?.master
</script>

<template>
  <main class="grid gap-5 p-4 lg:p-6 xl:grid-cols-[1.5fr_1fr]">
    <section>
      <h1 class="font-sign text-3xl font-semibold">{{ $t('reviews.title') }}</h1>
      <ul class="mt-4 space-y-2">
        <li
          v-for="r in reviews.data.value ?? []"
          :key="r.id"
          class="flex gap-3 rounded-2xl border border-line bg-surface p-4"
        >
          <MasterAvatar
            v-if="master(r.master_id)"
            :master="master(r.master_id)!"
            :lang="lang"
            :size="36"
          />
          <div class="min-w-0 flex-1">
            <p class="flex flex-wrap items-baseline justify-between gap-2">
              <span class="font-semibold">{{ r.client }}</span>
              <span class="text-xs text-muted">{{ day(r.created_at, lang, tz) }}</span>
            </p>
            <p class="text-brass" :aria-label="`${r.rating}/5`">
              {{ '★'.repeat(r.rating)
              }}<span class="text-line">{{ '★'.repeat(5 - r.rating) }}</span>
              <span class="ml-2 text-xs text-muted">{{ r.service[lang] }}</span>
            </p>
            <p v-if="r.comment" class="mt-1 text-sm">{{ r.comment }}</p>
          </div>
        </li>
      </ul>
    </section>
    <section>
      <h2 class="font-sign text-3xl font-semibold">{{ $t('reviews.waitlist') }}</h2>
      <ul class="mt-4 space-y-2">
        <li
          v-for="w in waitlist.data.value ?? []"
          :key="w.id"
          class="rounded-2xl border border-line bg-surface p-4 text-sm"
        >
          <p class="flex justify-between gap-2">
            <span class="font-semibold">{{ w.client.name }}</span>
            <span class="rounded-full bg-surface-2 px-2 py-0.5 text-xs">{{
              $t(`waitlistStatus.${w.status}`)
            }}</span>
          </p>
          <p class="mt-1 text-muted">
            {{ w.service[lang] }} · {{ day(w.day, lang, tz, true) }}
            <template v-if="master(w.master_id)"> · {{ master(w.master_id)!.name[lang] }}</template>
          </p>
          <p class="mt-1 text-xs text-faint">{{ dateTime(w.created_at, lang, tz) }}</p>
        </li>
        <li v-if="waitlist.data.value && !waitlist.data.value.length" class="text-muted">
          {{ $t('common.noData') }}
        </li>
      </ul>
    </section>
  </main>
</template>
