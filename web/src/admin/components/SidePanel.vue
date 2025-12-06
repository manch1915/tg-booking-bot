<script setup lang="ts">
import { onKeyStroke } from '@vueuse/core'
import { X } from 'lucide-vue-next'

const open = defineModel<boolean>({ required: true })
defineProps<{ title: string; subtitle?: string }>()

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
      <div v-if="open" class="fixed inset-0 z-40 bg-black/30" @click="open = false" />
    </Transition>
    <Transition
      enter-from-class="translate-x-full"
      leave-to-class="translate-x-full"
      enter-active-class="transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)]"
      leave-active-class="transition-transform duration-200 ease-in"
    >
      <aside
        v-if="open"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        class="fixed inset-y-0 right-0 z-50 flex w-full max-w-[440px] flex-col border-l border-line bg-surface shadow-2xl"
      >
        <header class="flex items-start gap-3 border-b border-line px-5 py-4">
          <div class="min-w-0 flex-1">
            <h2 class="font-sign text-2xl leading-tight font-semibold">{{ title }}</h2>
            <p v-if="subtitle" class="mt-0.5 text-sm text-muted">{{ subtitle }}</p>
          </div>
          <button
            type="button"
            class="grid size-9 place-items-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink"
            :aria-label="$t('common.close')"
            @click="open = false"
          >
            <X :size="18" />
          </button>
        </header>
        <div class="flex-1 overflow-y-auto px-5 py-4">
          <slot />
        </div>
        <footer v-if="$slots.footer" class="border-t border-line px-5 py-4">
          <slot name="footer" />
        </footer>
      </aside>
    </Transition>
  </Teleport>
</template>
