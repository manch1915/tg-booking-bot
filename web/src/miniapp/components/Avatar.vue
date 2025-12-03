<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{ src: string; name: string; color?: string; size?: number }>(),
  {
    color: 'var(--accent)',
    size: 48,
  },
)
const broken = ref(false)
const initials = computed(() =>
  props.name
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0] ?? '')
    .join(''),
)
</script>

<template>
  <span
    class="relative inline-grid shrink-0 place-items-center overflow-hidden rounded-full font-sign font-semibold text-white"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      background: color,
      fontSize: `${size * 0.38}px`,
    }"
  >
    <img
      v-if="src && !broken"
      :src="src"
      :alt="name"
      class="size-full object-cover"
      loading="lazy"
      @error="broken = true"
    />
    <span v-else aria-hidden="true">{{ initials }}</span>
  </span>
</template>
