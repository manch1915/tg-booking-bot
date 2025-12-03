<script setup lang="ts">
import { onKeyStroke } from '@vueuse/core'

const open = defineModel<boolean>({ required: true })
defineProps<{ title: string }>()

onKeyStroke('Escape', () => (open.value = false))
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-150"
    >
      <div v-if="open" class="fixed inset-0 z-40 bg-black/40" @click="open = false" />
    </Transition>
    <Transition
      enter-from-class="translate-y-full"
      leave-to-class="translate-y-full"
      enter-active-class="transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]"
      leave-active-class="transition-transform duration-200 ease-in"
    >
      <section
        v-if="open"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        class="fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[85vh] max-w-[480px] overflow-y-auto rounded-t-[22px] bg-surface px-5 pt-3 pb-[max(20px,env(safe-area-inset-bottom))]"
      >
        <div class="mx-auto mb-4 h-1 w-10 rounded-full bg-line" aria-hidden="true" />
        <h2 class="font-sign text-2xl font-semibold">{{ title }}</h2>
        <slot />
      </section>
    </Transition>
  </Teleport>
</template>
