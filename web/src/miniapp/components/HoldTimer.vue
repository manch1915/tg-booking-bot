<script setup lang="ts">
import { useIntervalFn } from '@vueuse/core'
import { computed, ref } from 'vue'

const props = defineProps<{ until: string; total: number }>()
const emit = defineEmits<{ expired: [] }>()
const now = ref(Date.now())

const left = computed(() => Math.max(0, new Date(props.until).getTime() - now.value))
const share = computed(() => Math.min(1, left.value / (props.total * 60_000)))
const label = computed(() => {
  const seconds = Math.ceil(left.value / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
})

const { pause } = useIntervalFn(() => {
  now.value = Date.now()
  if (left.value === 0) {
    pause()
    emit('expired')
  }
}, 1000)
</script>

<template>
  <!-- A barber pole that shrinks while the slot is held for the client. -->
  <div class="rounded-[18px] bg-surface p-4">
    <div class="flex items-baseline justify-between gap-3">
      <p class="font-semibold">{{ $t('pay.holding') }}</p>
      <p class="font-sign text-2xl font-semibold whitespace-nowrap num" aria-live="off">
        {{ $t('pay.left', { time: label }) }}
      </p>
    </div>
    <div
      class="mt-3 h-3 overflow-hidden rounded-full bg-surface-2"
      role="progressbar"
      :aria-valuenow="Math.round(share * 100)"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div
        class="pole h-full rounded-full transition-[width] duration-1000 ease-linear"
        :style="{ width: `${share * 100}%` }"
      />
    </div>
  </div>
</template>
