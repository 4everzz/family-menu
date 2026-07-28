import { createRouter, createWebHashHistory } from 'vue-router';
import { auth } from './store.js';

// 用 hash 模式，静态托管不需要额外的服务端 rewrite 配置。
const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('./components/AppLayout.vue'),
    children: [
      { path: '', redirect: '/overview' },
      { path: 'overview', name: 'overview', component: () => import('./views/Overview.vue'), meta: { title: '跨店总览' } },
      { path: 'orders', name: 'orders', component: () => import('./views/Orders.vue'), meta: { title: '跨店订单' } },
      { path: 'shops', name: 'shops', component: () => import('./views/Shops.vue'), meta: { title: '店铺管理' } },
      { path: 'members', name: 'members', component: () => import('./views/Members.vue'), meta: { title: '管理员授权' } },
      { path: 'users', name: 'users', component: () => import('./views/Users.vue'), meta: { title: '用户管理' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/overview' },
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
    return { name: 'overview' };
  }
  return true;
});

export default router;
