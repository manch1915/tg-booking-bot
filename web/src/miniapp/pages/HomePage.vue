<script setup lang="ts">
import { MapPin, Star } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { Schemas } from '@/shared/api/client'
import { dateTime, minutesLabel, money } from '@/shared/format'
import { photo } from '@/shared/photo'

import Avatar from '../components/Avatar.vue'
import LoadState from '../components/LoadState.vue'
import { draft, resetDraft } from '../draft'
import { useBookings, useCatalog } from '../queries'
import { locale, session } from '../session'
import { haptic, inTelegram } from '../telegram'

const router = useRouter()
const catalog = useCatalog()
const bookings = useBookings()
const activeCategory = ref<number | null>(null)

const business = computed(() => session.business!)
const lang = computed(() => locale())
const tz = computed(() => business.value.timezone)

const services = computed(() => catalog.data.value?.categories.flatMap((c) => c.services) ?? [])
const popular = computed(() => services.value.filter((s) => s.is_popular))
const categories = computed(() => catalog.data.value?.categories ?? [])
const visible = computed(() =>
  activeCategory.value === null
    ? categories.value
    : categories.value.filter((c) => c.id === activeCategory.value),
)
const nextVisit = computed(
  () =>
    (bookings.data.value ?? [])
      .filter((b) => b.status === 'confirmed' || b.status === 'pending_payment')
      .filter((b) => new Date(b.ends_at) > new Date())
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0],
)

function price(cents: number): string {
  return money(cents, business.value.currency, lang.value)
}

function open(service: Schemas['ServiceOut']): void {
  haptic('light')
  resetDraft()
  draft.serviceId = service.id
  void router.push({ name: 'service', params: { id: service.id } })
}

function pickCategory(id: number | null): void {
  haptic()
  activeCategory.value = id
}
</script>

<template>
  <main>
    <section class="px-4 pt-5 pb-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="min-h-5 text-sm text-muted">
            <template v-if="session.client">{{
              $t('home.hello', { name: session.client.name })
            }}</template>
          </p>
          <h1 class="mt-1 font-sign text-[40px] leading-[0.95] font-bold tracking-[0.005em]">
            {{ business.name }}
          </h1>
        </div>
        <span
          v-if="!inTelegram"
          class="mt-1 rounded-full bg-brass-soft px-2.5 py-1 text-xs font-bold text-brass"
          :title="$t('common.demoNote')"
        >
          {{ $t('common.demoBadge') }}
        </span>
      </div>
      <p class="mt-2 max-w-[34ch] text-[15px] leading-snug text-muted">
        {{ business.tagline[lang] }}
      </p>
      <p class="mt-3 flex items-center gap-1.5 text-sm text-ink">
        <MapPin :size="16" :stroke-width="1.75" class="text-accent" />
        {{ business.address }}
        <span class="text-faint">·</span>
        <span class="text-muted">{{ $t('home.openToday') }}</span>
      </p>
    </section>

    <RouterLink
      v-if="nextVisit"
      to="/bookings"
      class="mx-4 mb-4 flex items-center gap-3 rounded-[18px] bg-accent p-4 text-accent-ink"
    >
      <div class="min-w-0 flex-1">
        <p class="text-xs font-semibold opacity-80">{{ $t('home.next') }}</p>
        <p class="mt-0.5 font-sign text-2xl leading-tight font-semibold num">
          {{ dateTime(nextVisit.starts_at, lang, tz) }}
        </p>
        <p class="truncate text-sm opacity-90">
          {{ nextVisit.service.name[lang] }} · {{ nextVisit.master.name[lang] }}
        </p>
      </div>
      <Avatar
        :src="nextVisit.master.photo_url"
        :name="nextVisit.master.name[lang]"
        :color="nextVisit.master.color"
        :size="48"
      />
    </RouterLink>

    <LoadState
      :loading="catalog.isPending.value"
      :error="catalog.isError.value"
      @retry="catalog.refetch()"
    />

    <template v-if="catalog.data.value">
      <section v-if="popular.length" class="mb-6">
        <h2 class="px-4 pb-2 font-sign text-xl font-semibold">{{ $t('home.popular') }}</h2>
        <div
          class="flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1 [scrollbar-width:none]"
        >
          <button
            v-for="(service, index) in popular"
            :key="service.id"
            type="button"
            class="w-[148px] shrink-0 snap-start overflow-hidden rounded-[18px] bg-surface text-left transition-transform active:scale-[0.98]"
            @click="open(service)"
          >
            <div class="aspect-[4/5] bg-surface-2">
              <img
                :src="photo(service.photo_url, 148, 185)"
                :alt="service.name[lang]"
                class="size-full object-cover"
                width="148"
                height="185"
                :loading="index < 2 ? 'eager' : 'lazy'"
                :fetchpriority="index === 0 ? 'high' : 'auto'"
              />
            </div>
            <div class="p-3">
              <p class="line-clamp-2 text-sm leading-tight font-semibold">
                {{ service.name[lang] }}
              </p>
              <p class="mt-1 font-sign text-lg font-semibold text-accent num">
                {{ $t('common.from', { price: price(service.price_from) }) }}
              </p>
            </div>
          </button>
        </div>
      </section>

      <div
        class="sticky top-0 z-10 flex gap-2 overflow-x-auto bg-bg/95 px-4 py-2 backdrop-blur [scrollbar-width:none]"
        role="tablist"
      >
        <button
          type="button"
          role="tab"
          :aria-selected="activeCategory === null"
          class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors"
          :class="activeCategory === null ? 'bg-ink text-bg' : 'bg-surface text-muted'"
          @click="pickCategory(null)"
        >
          {{ $t('common.all') }}
        </button>
        <button
          v-for="category in categories"
          :key="category.id"
          type="button"
          role="tab"
          :aria-selected="activeCategory === category.id"
          class="shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors"
          :class="activeCategory === category.id ? 'bg-ink text-bg' : 'bg-surface text-muted'"
          @click="pickCategory(category.id)"
        >
          {{ category.name[lang] }}
        </button>
      </div>

      <section v-for="category in visible" :key="category.id" class="px-4 pt-4">
        <h2 class="pb-2 font-sign text-xl font-semibold">{{ category.name[lang] }}</h2>
        <ul class="divide-y divide-line overflow-hidden rounded-[18px] bg-surface">
          <li v-for="service in category.services" :key="service.id">
            <button
              type="button"
              class="flex w-full items-center gap-3 p-3 text-left transition-colors active:bg-surface-2"
              @click="open(service)"
            >
              <img
                :src="photo(service.photo_url, 56)"
                alt=""
                width="56"
                height="56"
                class="size-14 shrink-0 rounded-xl bg-surface-2 object-cover"
                loading="lazy"
              />
              <span class="min-w-0 flex-1">
                <span class="block truncate font-semibold">{{ service.name[lang] }}</span>
                <span class="text-sm text-muted">
                  {{ minutesLabel(service.duration_minutes, lang) }}
                </span>
              </span>
              <span class="font-sign text-lg font-semibold num">
                {{ $t('common.from', { price: price(service.price_from) }) }}
              </span>
            </button>
          </li>
        </ul>
      </section>

      <section class="pt-6">
        <h2 class="px-4 pb-2 font-sign text-xl font-semibold">{{ $t('home.team') }}</h2>
        <div class="flex gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none]">
          <article
            v-for="master in catalog.data.value.masters"
            :key="master.id"
            class="w-[132px] shrink-0 rounded-[18px] bg-surface p-3"
          >
            <Avatar
              :src="master.photo_url"
              :name="master.name[lang]"
              :color="master.color"
              :size="56"
            />
            <p class="mt-2 text-sm leading-tight font-semibold">{{ master.name[lang] }}</p>
            <p class="text-xs text-muted">{{ master.title[lang] }}</p>
            <p v-if="master.rating" class="mt-1 flex items-center gap-1 text-xs font-semibold">
              <Star :size="12" class="fill-brass text-brass" />
              <span class="num">{{ master.rating.toFixed(1) }}</span>
              <span class="font-normal text-faint">
                {{ $t('home.reviews', { n: master.reviews }, master.reviews) }}
              </span>
            </p>
          </article>
        </div>
      </section>
    </template>
  </main>
</template>
