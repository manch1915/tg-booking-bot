import { createRouter, createWebHistory } from 'vue-router'

import { auth, loadAdmin } from './api'

export const router = createRouter({
  history: createWebHistory('/admin/'),
  routes: [
    { path: '/login', name: 'login', component: () => import('./pages/LoginPage.vue') },
    {
      path: '/',
      component: () => import('./components/AdminLayout.vue'),
      children: [
        { path: '', redirect: '/journal' },
        { path: 'journal', name: 'journal', component: () => import('./pages/JournalPage.vue') },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('./pages/DashboardPage.vue'),
        },
        { path: 'clients', name: 'clients', component: () => import('./pages/ClientsPage.vue') },
        { path: 'masters', name: 'masters', component: () => import('./pages/MastersPage.vue') },
        { path: 'services', name: 'services', component: () => import('./pages/ServicesPage.vue') },
        {
          path: 'broadcasts',
          name: 'broadcasts',
          component: () => import('./pages/BroadcastsPage.vue'),
        },
        { path: 'reviews', name: 'reviews', component: () => import('./pages/ReviewsPage.vue') },
        { path: 'settings', name: 'settings', component: () => import('./pages/SettingsPage.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/journal' },
  ],
})

router.beforeEach(async (to) => {
  if (!auth.checked) await loadAdmin()
  if (!auth.admin && to.name !== 'login') return { name: 'login', query: { next: to.fullPath } }
  if (auth.admin && to.name === 'login') return '/journal'
  return true
})
