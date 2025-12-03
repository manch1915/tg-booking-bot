import '@/styles/base.css'

import { VueQueryPlugin } from '@tanstack/vue-query'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'

createApp(App)
  .use(i18n)
  .use(router)
  .use(VueQueryPlugin, {
    queryClientConfig: { defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } },
  })
  .mount('#app')
