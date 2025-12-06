<script setup lang="ts">
import { ref } from 'vue'

import type { Schemas } from '@/shared/api/client'

withDefaults(defineProps<{ master: Schemas['MasterOut']; lang: 'ru' | 'en'; size?: number }>(), {
  size: 36,
})
const broken = ref(false)
</script>

<template>
  <span
    class="inline-grid shrink-0 place-items-center overflow-hidden rounded-full font-sign font-semibold text-white ring-2"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      background: master.color,
      fontSize: `${size * 0.4}px`,
      '--tw-ring-color': master.color,
    }"
  >
    <img
      v-if="master.photo_url && !broken"
      :src="master.photo_url"
      :alt="master.name[lang]"
      class="size-full object-cover"
      loading="lazy"
      @error="broken = true"
    />
    <span v-else aria-hidden="true">{{ master.name[lang].slice(0, 1) }}</span>
  </span>
</template>
