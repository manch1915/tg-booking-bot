<script setup lang="ts">
import { useDark } from '@vueuse/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed } from 'vue'
import VChart from 'vue-echarts'

import type { Schemas } from '@/shared/api/client'
import { day } from '@/shared/format'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  points: Schemas['DayPoint'][]
  lang: 'ru' | 'en'
  tz: string
  format: (cents: number) => string
}>()
const dark = useDark({ storageKey: 'bb.admin-theme' })

const css = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

const option = computed(() => {
  // Recomputed on theme change so the chart picks up the new CSS colours.
  void dark.value
  const ink = css('--muted')
  const line = css('--line')
  return {
    animationDuration: 400,
    grid: { left: 8, right: 8, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: css('--surface'),
      borderColor: line,
      textStyle: { color: css('--ink'), fontFamily: 'Manrope Variable' },
      valueFormatter: (value: number) => props.format(value),
    },
    xAxis: {
      type: 'category',
      data: props.points.map((p) => day(p.day, props.lang, props.tz)),
      axisLine: { lineStyle: { color: line } },
      axisTick: { show: false },
      axisLabel: { color: ink, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: line, type: 'dashed' } },
      axisLabel: { color: ink, fontSize: 11, formatter: (v: number) => props.format(v) },
    },
    series: [
      {
        type: 'bar',
        data: props.points.map((p) => p.revenue),
        barMaxWidth: 22,
        itemStyle: { color: css('--accent'), borderRadius: [4, 4, 0, 0] },
        emphasis: { itemStyle: { color: css('--brass') } },
      },
    ],
  }
})
</script>

<template>
  <VChart
    :option="option"
    autoresize
    class="h-[280px] w-full"
    role="img"
    aria-label="Revenue by day"
  />
</template>
