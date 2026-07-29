<script setup>
import { computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { auth } from '../store.js';
import { callApi } from '../api.js';

const router = useRouter();
const route = useRoute();

const nav = [
  { name: 'overview', label: '跨店总览', hint: '平台今日经营' },
  { name: 'orders', label: '跨店订单', hint: '筛选与订单详情' },
  { name: 'reports', label: '经营报表', hint: '跨店经营分析' },
  { name: 'backups', label: '数据备份', hint: '店铺配置与订单留存' },
  { name: 'shops', label: '店铺管理', hint: '建店与启停' },
  { name: 'members', label: '管理员授权', hint: '指派一级 / 二级' },
  { name: 'users', label: '用户管理', hint: '搜索与停用账号' },
];

const currentTitle = computed(() => route.meta.title || '平台后台');
const initial = computed(() => (auth.username || '·').slice(0, 1).toUpperCase());

async function logout() {
  await callApi('logout', { token: auth.token }, { withToken: false });
  auth.clear();
  router.replace({ name: 'login' });
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">小家</div>
        <div class="brand-text">
          <div class="brand-name">小家菜单</div>
          <div class="brand-sub">平台控制台</div>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in nav"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          :class="{ active: route.name === item.name }"
        >
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-hint">{{ item.hint }}</span>
        </router-link>
      </nav>

      <div class="sidebar-foot">
        <div class="who">
          <div class="who-avatar">{{ initial }}</div>
          <div class="who-name">{{ auth.username }}</div>
        </div>
        <button class="logout" @click="logout">退出登录</button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <h1 class="topbar-title">{{ currentTitle }}</h1>
        <span class="topbar-tag">超级管理员</span>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell { display: flex; min-height: 100vh; }

.sidebar {
  width: 244px;
  flex: none;
  background: var(--sidebar);
  color: var(--sidebar-ink);
  display: flex;
  flex-direction: column;
  padding: 22px 16px;
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand { display: flex; align-items: center; gap: 11px; padding: 4px 6px 22px; }
.brand-mark {
  width: 40px; height: 40px;
  border-radius: 11px;
  background: linear-gradient(150deg, var(--accent), #3f8f75);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; letter-spacing: 0.02em;
}
.brand-name { color: #fff; font-weight: 650; font-size: 15px; }
.brand-sub { color: var(--sidebar-ink-dim); font-size: 12px; margin-top: 1px; }

.nav { display: flex; flex-direction: column; gap: 3px; }
.nav-item {
  display: flex; flex-direction: column; gap: 1px;
  padding: 10px 12px;
  border-radius: 9px;
  border-left: 2px solid transparent;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover { background: rgba(255, 255, 255, 0.05); }
.nav-item.active {
  background: rgba(63, 143, 117, 0.16);
  border-left-color: var(--accent);
}
.nav-label { font-size: 14px; font-weight: 550; color: var(--sidebar-ink); }
.nav-item.active .nav-label { color: #fff; }
.nav-hint { font-size: 11.5px; color: var(--sidebar-ink-dim); }

.sidebar-foot { margin-top: auto; padding-top: 18px; border-top: 1px solid rgba(255,255,255,0.07); }
.who { display: flex; align-items: center; gap: 10px; padding: 4px 6px 12px; }
.who-avatar {
  width: 30px; height: 30px; border-radius: 50%;
  background: rgba(255,255,255,0.1); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.who-name { font-size: 13.5px; color: var(--sidebar-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.logout {
  width: 100%;
  height: 34px;
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 8px;
  background: transparent;
  color: var(--sidebar-ink);
  font-size: 13px;
  transition: background 0.15s;
}
.logout:hover { background: rgba(255,255,255,0.07); }

.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.topbar {
  height: 62px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 30px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  position: sticky; top: 0; z-index: 10;
}
.topbar-title { font-size: 17px; font-weight: 650; }
.topbar-tag {
  font-size: 12px; font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent-soft);
  padding: 3px 10px; border-radius: 100px;
}
.content { padding: 26px 30px 40px; max-width: 1080px; width: 100%; }

@media (max-width: 720px) {
  .sidebar { width: 74px; padding: 18px 10px; }
  .brand-text, .nav-hint, .who-name, .brand-sub { display: none; }
  .nav-item { align-items: center; }
  .content { padding: 20px 16px 32px; }
  .topbar { padding: 0 16px; }
}
</style>
