<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { day } from '@/shared/format'

const props = defineProps<{
  points: Schemas['DayPoint'][]
  lang: 'ru' | 'en'
  tz: string
  format: (cents: number) => string
}>()

const WIDTH = 640
const HEIGHT = 240
const PAD = { top: 12, right: 8, bottom: 26, left: 56 }
const hovered = ref<number | null>(null)

const max = computed(() => {
  const top = Math.max(...props.points.map((p) => p.revenue), 1)
  // Round the axis up to a tidy step so the grid lines land on round sums.
  const step = 10 ** Math.floor(Math.log10(top))
  return Math.ceil(top / step) * step
})
const plotW = WIDTH - PAD.left - PAD.right
const plotH = HEIGHT - PAD.top - PAD.bottom
const slot = computed(() => plotW / Math.max(1, props.points.length))
const barW = computed(() => Math.max(3, Math.min(22, slot.value * 0.62)))
const ticks = computed(() => [0, 0.25, 0.5, 0.75, 1].map((t) => t * max.value))
const labelEvery = computed(() => Math.ceil(props.points.length / 8))

const y = (value: number) => PAD.top + plotH - (value / max.value) * plotH
const x = (index: number) => PAD.left + index * slot.value + (slot.value - barW.value) / 2
</script>

<template>
  <figure class="relative mt-2">
    <svg
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      class="h-[260px] w-full"
      role="img"
      :aria-label="$t('dashboard.byDay')"
      preserveAspectRatio="none"
    >
      <g class="text-[11px]">
        <template v-for="tick in ticks" :key="tick">
          <line
            :x1="PAD.left"
            :x2="WIDTH - PAD.right"
            :y1="y(tick)"
            :y2="y(tick)"
            stroke="var(--line)"
            stroke-dasharray="3 4"
          />
          <text :x="PAD.left - 8" :y="y(tick) + 4" text-anchor="end" fill="var(--faint)">
            {{ format(tick) }}
          </text>
        </template>
        <template v-for="(point, i) in points" :key="point.day">
          <rect
            :x="x(i)"
            :y="y(point.revenue)"
            :width="barW"
            :height="Math.max(0, PAD.top + plotH - y(point.revenue))"
            rx="3"
            :fill="hovered === i ? 'var(--brass)' : 'var(--accent)'"
            @mouseenter="hovered = i"
            @mouseleave="hovered = null"
          />
          <text
            v-if="i % labelEvery === 0"
            :x="x(i) + barW / 2"
            :y="HEIGHT - 8"
            text-anchor="middle"
            fill="var(--faint)"
          >
            {{ day(point.day, lang, tz).split(',').pop() }}
          </text>
        </template>
      </g>
    </svg>
    <figcaption
      v-if="hovered !== null && points[hovered]"
      class="pointer-events-none absolute top-0 right-0 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm shadow-sm"
    >
      <span class="text-muted">{{ day(points[hovered]!.day, lang, tz) }}</span>
      <span class="ml-2 font-semibold num">{{ format(points[hovered]!.revenue) }}</span>
      <span class="ml-1 text-muted num">· {{ points[hovered]!.visits }}</span>
    </figcaption>
  </figure>
</template>
