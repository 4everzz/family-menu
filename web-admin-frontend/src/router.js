import { createRouter, createWebHashHistory } from 'vue-router';
import { auth } from './store.js';

// 用 hash 模式，静态托管不需要额外的服务端 rewrite 配置。
const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('./components/AppLayout.vue'),
    children: [
      { path: '', redirect: { name: 'operations', query: { tab: 'overview' } } },
      { path: 'operations', name: 'operations', component: () => import('./views/Operations.vue'), meta: { title: '经营中心' } },
      { path: 'shops', name: 'shops', component: () => import('./views/ShopManagement.vue'), meta: { title: '店铺管理' } },
      { path: 'accounts', name: 'accounts', component: () => import('./views/Accounts.vue'), meta: { title: '账号与权限' } },
      { path: 'overview', redirect: { name: 'operations', query: { tab: 'overview' } } },
      { path: 'orders', redirect: { name: 'operations', query: { tab: 'orders' } } },
      { path: 'reports', redirect: { name: 'shops', query: { tab: 'reports' } } },
      { path: 'backups', redirect: { name: 'shops', query: { tab: 'backups' } } },
      { path: 'members', redirect: { name: 'accounts', query: { tab: 'members' } } },
      { path: 'users', redirect: { name: 'accounts', query: { tab: 'users' } } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'operations', query: { tab: 'overview' } } },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  if (!to.meta.public && !auth.isLoggedIn) {
    return { name: 'login', query: to.name ? { redirect: to.fullPath } : {} };
  }
  if (to.name === 'login' && auth.isLoggedIn) {
    return { name: 'operations', query: { tab: 'overview' } };
  }
  return true;
});

export default router;
