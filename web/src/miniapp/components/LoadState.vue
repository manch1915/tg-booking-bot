<script setup lang="ts">
defineProps<{ error?: boolean; loading?: boolean; lines?: number }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="error" class="mx-4 my-6 rounded-2xl bg-surface p-5 text-center" role="alert">
    <p class="text-sm text-muted">{{ $t('common.loadError') }}</p>
    <button
      type="button"
      class="mt-3 rounded-full bg-accent-soft px-4 py-2 text-sm font-semibold text-accent"
      @click="$emit('retry')"
    >
      {{ $t('common.retry') }}
    </button>
  </div>
  <div v-else-if="loading" class="space-y-3 px-4 py-4" aria-busy="true">
    <div
      v-for="n in lines ?? 3"
      :key="n"
      class="h-20 animate-pulse rounded-2xl bg-surface"
      :style="{ opacity: 1 - n * 0.2 }"
    />
  </div>
</template>
