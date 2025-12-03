import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory('/app/'),
  routes: [
    { path: '/', name: 'home', component: () => import('./pages/HomePage.vue') },
    {
      path: '/service/:id',
      name: 'service',
      component: () => import('./pages/ServicePage.vue'),
      props: (route) => ({ id: Number(route.params.id) }),
    },
    { path: '/time', name: 'time', component: () => import('./pages/TimePage.vue') },
    { path: '/confirm', name: 'confirm', component: () => import('./pages/ConfirmPage.vue') },
    {
      path: '/booking/:id/pay',
      name: 'pay',
      component: () => import('./pages/PayPage.vue'),
      props: (route) => ({ id: Number(route.params.id) }),
    },
    {
      path: '/booking/:id/done',
      name: 'done',
      component: () => import('./pages/DonePage.vue'),
      props: (route) => ({ id: Number(route.params.id) }),
    },
    { path: '/bookings', name: 'bookings', component: () => import('./pages/BookingsPage.vue') },
    { path: '/profile', name: 'profile', component: () => import('./pages/ProfilePage.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
