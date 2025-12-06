<script setup lang="ts">
import MasterEditor from '../components/MasterEditor.vue'
import { useMasters } from '../context'

const masters = useMasters()
</script>

<template>
  <main class="space-y-4 p-4 lg:p-6">
    <h1 class="font-sign text-3xl font-semibold">{{ $t('nav.masters') }}</h1>
    <p v-if="masters.isError.value" class="rounded-xl bg-danger-soft p-4 text-danger" role="alert">
      {{ $t('common.error') }}
    </p>
    <div v-if="!masters.data.value" class="h-96 animate-pulse rounded-2xl bg-surface" />
    <MasterEditor v-for="item in masters.data.value ?? []" :key="item.master.id" :item="item" />
  </main>
</template>
