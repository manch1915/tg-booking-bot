<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Plus } from 'lucide-vue-next'
import { ref } from 'vue'

import type { Schemas } from '@/shared/api/client'
import { minutesLabel } from '@/shared/format'

import { api } from '../api'
import SidePanel from '../components/SidePanel.vue'
import { useServices, useShop } from '../context'

const queryClient = useQueryClient()
const { lang, fmt } = useShop()
const services = useServices()
const categories = useQuery({
  queryKey: ['admin', 'categories'],
  queryFn: () => api.get<Schemas['CategoryOutAdmin'][]>('/api/admin/categories'),
})

const open = ref(false)
const editingId = ref<number | null>(null)
const blank = () => ({
  category_id: categories.data.value?.[0]?.id ?? 1,
  name_ru: '',
  name_en: '',
  description_ru: '',
  description_en: '',
  duration_minutes: 30,
  price: 20,
  photo_url: '',
  is_popular: false,
  is_active: true,
})
const form = ref(blank())

function edit(s?: Schemas['AdminServiceOut']): void {
  editingId.value = s?.id ?? null
  form.value = s
    ? {
        category_id: s.category_id,
        name_ru: s.name.ru,
        name_en: s.name.en,
        description_ru: s.description.ru,
        description_en: s.description.en,
        duration_minutes: s.duration_minutes,
        price: s.price / 100,
        photo_url: s.photo_url,
        is_popular: s.is_popular,
        is_active: s.is_active,
      }
    : blank()
  open.value = true
}

const save = useMutation({
  mutationFn: () => {
    const body = { ...form.value, price: Math.round(form.value.price * 100) }
    return editingId.value
      ? api.put(`/api/admin/services/${editingId.value}`, body)
      : api.post('/api/admin/services', body)
  },
  onSuccess: async () => {
    open.value = false
    await queryClient.invalidateQueries({ queryKey: ['admin', 'services'] })
  },
})
</script>

<template>
  <main class="space-y-4 p-4 lg:p-6">
    <header class="flex items-center gap-3">
      <h1 class="mr-auto font-sign text-3xl font-semibold">{{ $t('nav.services') }}</h1>
      <button
        type="button"
        class="flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-sm font-semibold text-accent-ink"
        @click="edit()"
      >
        <Plus :size="16" /> {{ $t('services.add') }}
      </button>
    </header>

    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <button
        v-for="s in services.data.value ?? []"
        :key="s.id"
        type="button"
        class="flex gap-3 rounded-2xl border border-line bg-surface p-3 text-left transition-colors hover:border-accent"
        :class="{ 'opacity-50': !s.is_active }"
        @click="edit(s)"
      >
        <img
          :src="s.photo_url"
          alt=""
          class="size-20 shrink-0 rounded-xl bg-surface-2 object-cover"
          loading="lazy"
        />
        <span class="min-w-0 flex-1">
          <span class="block text-xs text-muted">{{ s.category[lang] }}</span>
          <span class="block truncate font-semibold">{{ s.name[lang] }}</span>
          <span class="mt-1 flex items-baseline gap-2">
            <span class="font-sign text-xl font-semibold num">{{ fmt(s.price) }}</span>
            <span class="text-sm text-muted">{{ minutesLabel(s.duration_minutes, lang) }}</span>
          </span>
          <span class="text-xs text-faint">{{ $t('services.masters') }}: {{ s.masters }}</span>
        </span>
        <span
          v-if="s.is_popular"
          class="self-start rounded-full bg-brass-soft px-2 py-0.5 text-xs font-semibold text-brass"
        >
          {{ $t('services.popular') }}
        </span>
      </button>
    </div>

    <SidePanel v-model="open" :title="editingId ? $t('services.edit') : $t('services.add')">
      <form id="service-form" class="space-y-3" @submit.prevent="save.mutate()">
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('services.category') }}</span>
          <select
            v-model="form.category_id"
            class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-2"
          >
            <option v-for="c in categories.data.value ?? []" :key="c.id" :value="c.id">
              {{ c.name[lang] }}
            </option>
          </select>
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-sm font-semibold">{{ $t('services.name') }} RU</span>
            <input
              v-model="form.name_ru"
              required
              maxlength="120"
              class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
            />
          </label>
          <label class="block">
            <span class="text-sm font-semibold">{{ $t('services.name') }} EN</span>
            <input
              v-model="form.name_en"
              required
              maxlength="120"
              class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
            />
          </label>
          <label class="block">
            <span class="text-sm font-semibold">{{ $t('services.duration') }}</span>
            <input
              v-model.number="form.duration_minutes"
              type="number"
              min="5"
              max="480"
              step="5"
              required
              class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
            />
          </label>
          <label class="block">
            <span class="text-sm font-semibold">{{ $t('services.price') }}</span>
            <input
              v-model.number="form.price"
              type="number"
              min="0"
              step="0.5"
              required
              class="mt-1 h-10 w-full rounded-lg border border-line bg-surface px-3"
            />
          </label>
        </div>
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('services.description') }} RU</span>
          <textarea
            v-model="form.description_ru"
            rows="2"
            maxlength="1000"
            class="mt-1 w-full resize-none rounded-lg border border-line bg-surface p-2.5"
          />
        </label>
        <label class="block">
          <span class="text-sm font-semibold">{{ $t('services.description') }} EN</span>
          <textarea
            v-model="form.description_en"
            rows="2"
            maxlength="1000"
            class="mt-1 w-full resize-none rounded-lg border border-line bg-surface p-2.5"
          />
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="form.is_popular" type="checkbox" class="size-4 accent-[var(--accent)]" />
          {{ $t('services.popular') }}
        </label>
        <label class="flex items-center gap-2 text-sm">
          <input v-model="form.is_active" type="checkbox" class="size-4 accent-[var(--accent)]" />
          {{ $t('services.active') }}
        </label>
        <p v-if="save.isError.value" class="text-sm text-danger" role="alert">
          {{ save.error.value?.message }}
        </p>
      </form>
      <template #footer>
        <button
          type="submit"
          form="service-form"
          class="h-11 w-full rounded-lg bg-accent font-semibold text-accent-ink"
          :disabled="save.isPending.value"
        >
          {{ $t('common.save') }}
        </button>
      </template>
    </SidePanel>
  </main>
</template>
