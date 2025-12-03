<script setup lang="ts">
import { LoaderCircle } from 'lucide-vue-next'

import { mainAction } from '../composables/mainAction'
</script>

<template>
  <!-- Stand-in for Telegram's MainButton when the Mini App is opened in a browser. -->
  <Transition
    enter-from-class="translate-y-full opacity-0"
    leave-to-class="translate-y-full opacity-0"
    enter-active-class="transition duration-200 ease-out"
    leave-active-class="transition duration-150 ease-in"
  >
    <div
      v-if="mainAction.visible"
      class="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-[480px] border-t border-line bg-surface/95 px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))] backdrop-blur"
    >
      <button
        type="button"
        class="flex h-12 w-full items-center justify-center gap-2 rounded-[14px] bg-accent font-semibold text-accent-ink transition-[transform,opacity] active:scale-[0.98] disabled:bg-line disabled:text-muted"
        :disabled="mainAction.disabled || mainAction.loading"
        @click="mainAction.handler?.()"
      >
        <LoaderCircle v-if="mainAction.loading" :size="18" class="animate-spin" />
        {{ mainAction.text }}
      </button>
    </div>
  </Transition>
</template>
