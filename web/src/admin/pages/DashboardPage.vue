<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { Download, Star, TrendingDown, TrendingUp } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { addDays, todayIn } from '@/shared/zone'

import { api, downloadUrl } from '../api'
import MasterAvatar from '../components/MasterAvatar.vue'
import RevenueChart from '../components/RevenueChart.vue'
import { useMasters, useShop } from '../context'

const { lang, tz, fmt, business } = useShop()
const masters = useMasters()
const days = ref(30)

const period = computed(() => {
  // Yesterday is the last full day; today is still in progress.
  const end = addDays(todayIn(tz.value), -1)
  return { start: addDays(end, -(days.value - 1)), end }
})

const report = useQuery({
  queryKey: ['admin', 'report', period],
  queryFn: () => api.get<Schemas['ReportOut']>('/api/admin/reports', period.value),
  enabled: computed(() => !!business.data.value),
  placeholderData: (previous) => previous,
})

const reviews = useQuery({
  queryKey: ['admin', 'reviews'],
  queryFn: () => api.get<Schemas['ReviewRow'][]>('/api/admin/reviews'),
})

function change(current: number, previous: number): number | null {
  if (!previous) return null
  const delta = Math.round(((current - previous) / previous) * 100)
  // A tiny previous period gives meaningless numbers like +9000%.
  return Math.abs(delta) > 300 ? null : delta
}

const kpis = computed(() => {
  const r = report.data.value
  if (!r) return []
  return [
    {
      label: 'dashboard.revenue',
      value: fmt(r.revenue),
      delta: change(r.revenue, r.previous_revenue),
    },
    {
      label: 'dashboard.visits',
      value: String(r.visits),
      delta: change(r.visits, r.previous_visits),
    },
    { label: 'dashboard.avg', value: fmt(r.average_check), delta: null },
    { label: 'dashboard.load', value: `${Math.round(r.load * 100)}%`, delta: null },
    { label: 'dashboard.noShows', value: `${(r.no_show_rate * 100).toFixed(1)}%`, delta: null },
    { label: 'dashboard.newClients', value: String(r.new_clients), delta: null },
  ]
})

const masterRows = computed(() =>
  (report.data.value?.by_master ?? []).map((row) => ({
    ...row,
    master: masters.data.value?.find((m) => m.master.id === row.master_id)?.master,
  })),
)

function share(counts: Record<string, number>): { key: string; value: number; percent: number }[] {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, value, percent: Math.round((value / total) * 100) }))
}

const exportHref = computed(() => downloadUrl('/api/admin/bookings.csv', period.value))
</script>

<template>
  <main class="space-y-5 p-4 lg:p-6">
    <header class="flex flex-wrap items-center gap-3">
      <h1 class="mr-auto font-sign text-3xl font-semibold">{{ $t('nav.dashboard') }}</h1>
      <div
        class="flex rounded-lg border border-line bg-surface p-0.5 text-sm font-semibold"
        role="radiogroup"
        :aria-label="$t('dashboard.period')"
      >
        <button
          v-for="option in [7, 30, 90]"
          :key="option"
          type="button"
          role="radio"
          :aria-checked="days === option"
          class="rounded-md px-3 py-1.5"
          :class="days === option ? 'bg-ink text-bg' : 'text-muted'"
          @click="days = option"
        >
          {{ $t(`dashboard.days${option}`) }}
        </button>
      </div>
      <a
        :href="exportHref"
        class="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-sm font-semibold hover:bg-surface-2"
      >
        <Download :size="16" /> {{ $t('common.export') }}
      </a>
    </header>

    <p v-if="report.isError.value" class="rounded-xl bg-danger-soft p-4 text-danger" role="alert">
      {{ $t('common.error') }}
    </p>

    <section class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <article
        v-for="kpi in kpis"
        :key="kpi.label"
        class="rounded-2xl border border-line bg-surface p-4"
      >
        <p class="text-sm text-muted">{{ $t(kpi.label) }}</p>
        <p class="mt-1 font-sign text-[32px] leading-none font-semibold num">{{ kpi.value }}</p>
        <p
          v-if="kpi.delta !== null"
          class="mt-2 flex items-center gap-1 text-xs font-semibold"
          :class="kpi.delta >= 0 ? 'text-accent' : 'text-danger'"
          :title="$t('dashboard.vsPrev')"
        >
          <TrendingUp v-if="kpi.delta >= 0" :size="14" />
          <TrendingDown v-else :size="14" />
          <span class="num">{{ kpi.delta > 0 ? '+' : '' }}{{ kpi.delta }}%</span>
          <span class="font-normal text-faint">{{ $t('dashboard.vsPrev') }}</span>
        </p>
      </article>
      <template v-if="!report.data.value">
        <div v-for="n in 6" :key="n" class="h-[108px] animate-pulse rounded-2xl bg-surface" />
      </template>
    </section>

    <div class="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
      <section class="rounded-2xl border border-line bg-surface p-4">
        <h2 class="font-sign text-xl font-semibold">{{ $t('dashboard.byDay') }}</h2>
        <RevenueChart
          v-if="report.data.value"
          :points="report.data.value.by_day"
          :lang="lang"
          :tz="tz"
          :format="fmt"
        />
        <div v-else class="h-[280px] animate-pulse rounded-xl bg-surface-2" />
      </section>

      <section class="rounded-2xl border border-line bg-surface p-4">
        <h2 class="font-sign text-xl font-semibold">{{ $t('dashboard.masters') }}</h2>
        <ul class="mt-3 space-y-3">
          <li v-for="row in masterRows" :key="row.master_id" class="flex items-center gap-3">
            <MasterAvatar v-if="row.master" :master="row.master" :lang="lang" :size="36" />
            <div class="min-w-0 flex-1">
              <div class="flex items-baseline justify-between gap-2">
                <p class="truncate text-sm font-semibold">{{ row.master?.name[lang] }}</p>
                <p class="font-sign text-lg font-semibold num">{{ fmt(row.revenue) }}</p>
              </div>
              <div class="mt-1 flex items-center gap-2">
                <div
                  class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2"
                  role="meter"
                  :aria-valuenow="Math.round(row.load * 100)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                  :aria-label="$t('dashboard.load')"
                >
                  <div
                    class="h-full rounded-full"
                    :style="{
                      width: `${Math.min(100, row.load * 100)}%`,
                      background: row.master?.color,
                    }"
                  />
                </div>
                <span class="w-10 text-right text-xs text-muted num"
                  >{{ Math.round(row.load * 100) }}%</span
                >
              </div>
              <p class="mt-0.5 flex items-center gap-1 text-xs text-muted">
                <span class="num">{{ row.visits }}</span> ·
                {{ $t('dashboard.visits').toLowerCase() }}
                <template v-if="row.rating">
                  · <Star :size="12" class="fill-brass text-brass" />
                  <span class="num">{{ row.rating.toFixed(1) }}</span>
                </template>
              </p>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <div v-if="report.data.value" class="grid gap-5 lg:grid-cols-3">
      <section class="rounded-2xl border border-line bg-surface p-4">
        <h2 class="font-sign text-xl font-semibold">{{ $t('dashboard.services') }}</h2>
        <ol class="mt-3 space-y-2">
          <li
            v-for="s in report.data.value.by_service.slice(0, 6)"
            :key="s.service_id"
            class="flex items-baseline justify-between gap-3 text-sm"
          >
            <span class="truncate">{{ s.name[lang] }}</span>
            <span class="shrink-0 text-muted num">{{ s.visits }} · {{ fmt(s.revenue) }}</span>
          </li>
        </ol>
      </section>
      <section class="rounded-2xl border border-line bg-surface p-4">
        <h2 class="font-sign text-xl font-semibold">{{ $t('dashboard.sources') }}</h2>
        <ul class="mt-3 space-y-2.5">
          <li v-for="row in share(report.data.value.by_source)" :key="row.key" class="text-sm">
            <div class="flex justify-between">
              <span>{{ $t(`source.${row.key}`) }}</span
              ><span class="text-muted num">{{ row.percent }}%</span>
            </div>
            <div class="mt-1 h-1.5 rounded-full bg-surface-2">
              <div class="h-full rounded-full bg-accent" :style="{ width: `${row.percent}%` }" />
            </div>
          </li>
        </ul>
      </section>
      <section class="rounded-2xl border border-line bg-surface p-4">
        <h2 class="font-sign text-xl font-semibold">{{ $t('dashboard.methods') }}</h2>
        <ul class="mt-3 space-y-2.5">
          <li v-for="row in share(report.data.value.by_method)" :key="row.key" class="text-sm">
            <div class="flex justify-between">
              <span>{{ $t(`method.${row.key}`) }}</span
              ><span class="text-muted num">{{ row.percent }}%</span>
            </div>
            <div class="mt-1 h-1.5 rounded-full bg-surface-2">
              <div class="h-full rounded-full bg-brass" :style="{ width: `${row.percent}%` }" />
            </div>
          </li>
        </ul>
        <p class="mt-4 flex justify-between border-t border-line pt-3 text-sm">
          <span class="text-muted">{{ $t('dashboard.deposits') }}</span
          ><span class="num">{{ fmt(report.data.value.deposits) }}</span>
        </p>
      </section>
    </div>

    <section v-if="reviews.data.value" class="rounded-2xl border border-line bg-surface p-4">
      <h2 class="font-sign text-xl font-semibold">{{ $t('nav.reviews') }}</h2>
      <ul class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <li
          v-for="r in reviews.data.value.filter((r) => r.comment).slice(0, 6)"
          :key="r.id"
          class="rounded-xl bg-surface-2 p-3 text-sm"
        >
          <p class="text-brass" :aria-label="`${r.rating}/5`">
            {{ '★'.repeat(r.rating) }}<span class="text-line">{{ '★'.repeat(5 - r.rating) }}</span>
          </p>
          <p class="mt-1">{{ r.comment }}</p>
          <p class="mt-2 text-xs text-muted">{{ r.client }} · {{ r.service[lang] }}</p>
        </li>
      </ul>
    </section>
  </main>
</template>
