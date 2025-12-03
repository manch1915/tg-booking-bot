<script setup lang="ts">
import { ChevronLeft } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

import { useTelegramBack } from '../composables/backButton'
import { inTelegram } from '../telegram'

const props = defineProps<{ title?: string; back?: string | (() => void) }>()
const router = useRouter()

function goBack(): void {
  if (typeof props.back === 'function') props.back()
  else if (props.back) void router.push(props.back)
  else router.back()
}

if (props.back !== undefined) useTelegramBack(goBack)
</script>

<template>
  <header class="flex min-h-12 items-center gap-1 px-4 pt-3 pb-1">
    <button
      v-if="back !== undefined && !inTelegram"
      type="button"
      class="-ml-2 grid size-10 place-items-center rounded-full text-ink hover:bg-surface-2"
      :aria-label="$t('common.back')"
      @click="goBack"
    >
      <ChevronLeft :size="24" :stroke-width="2" />
    </button>
    <h1 v-if="title" class="font-sign text-[26px] leading-tight font-semibold tracking-[0.01em]">
      {{ title }}
    </h1>
    <div class="ml-auto"><slot /></div>
  </header>
</template>
