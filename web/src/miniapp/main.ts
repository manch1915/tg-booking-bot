import '@/styles/base.css'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createApp } from 'vue'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'
import { prefetchCatalog } from './session'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})
// The catalogue is public, so it loads while the client is still signing in.
prefetchCatalog(queryClient)

createApp(App).use(i18n).use(router).use(VueQueryPlugin, { queryClient }).mount('#app')
