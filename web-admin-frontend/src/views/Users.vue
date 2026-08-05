<script setup>
import { computed, onMounted, ref } from 'vue';
import { callApi } from '../api.js';

const loading = ref(true);
const error = ref('');
const users = ref([]);
const keyword = ref('');
const page = ref(1);
const pageSize = 30;
const hasMore = ref(false);
const busyId = ref('');
const toast = ref('');

const isSearching = computed(() => Boolean(keyword.value.trim()));

function avatarText(user) {
  return (user?.nickname || '微').slice(0, 1).toUpperCase();
}

function roleText(role) {
  if (role === 'super_admin') return '小程序超管';
  if (role === 'manager') return '历史管理员';
  return '普通用户';
}

function flash(message) {
  toast.value = message;
  setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2600);
}

async function load({ reset = false } = {}) {
  if (reset) page.value = 1;
  loading.value = true;
  error.value = '';
  const result = await callApi('listUsers', {
    keyword: keyword.value.trim(),
    page: page.value,
    pageSize,
  });
  loading.value = false;
  if (result.ok) {
    users.value = reset || page.value === 1 ? result.users : [...users.value, ...result.users];
    hasMore.value = result.hasMore === true;
  } else {
    error.value = result.message || '加载用户失败';
  }
}

async function search() {
  await load({ reset: true });
}

async function clearSearch() {
  keyword.value = '';
  await load({ reset: true });
}

async function loadMore() {
  if (!hasMore.value || loading.value) return;
  page.value += 1;
  await load();
}

async function toggleUser(user) {
  if (!user || busyId.value) return;
  busyId.value = user.id;
  const result = await callApi('setUserEnabled', { userId: user.id, enabled: !user.enabled });
  busyId.value = '';
  if (result.ok) {
    user.enabled = !user.enabled;
    flash(user.enabled ? '已启用该用户' : '已停用该用户');
  } else {
    flash(result.message || '操作失败');
  }
}

async function resetUserProfile(user) {
  if (!user || busyId.value) return;
  const confirmed = window.confirm(`确定重置“${user.nickname || '该用户'}”的昵称和头像吗？\n\n重置后会生成随机昵称并清空头像。系统 ID、订单、店铺关系和权限不会受影响；用户重新打开小程序后会收到重新完善资料的提示。`);
  if (!confirmed) return;

  busyId.value = user.id;
  const result = await callApi('resetUserProfile', { userId: user.id });
  busyId.value = '';
  if (result.ok) {
    user.nickname = result.user?.nickname || 'U0000000';
    user.avatarFileId = '';
    user.avatarUrl = '';
    user.profileCompleted = false;
    flash('用户资料已重置，对方重新打开小程序后会收到完善资料提示');
  } else {
    flash(result.message || '重置资料失败');
  }
}

onMounted(() => load({ reset: true }));
</script>

<template>
  <div class="spread page-head">
    <div>
      <p class="page-eyebrow">平台注册用户</p>
      <h2 class="page-title">用户管理</h2>
    </div>
    <button class="btn btn-sm" :disabled="loading" @click="load({ reset: true })">
      {{ loading ? '刷新中…' : '刷新' }}
    </button>
  </div>

  <section class="card search-card">
    <div class="search-main">
      <input
        v-model="keyword"
        class="input"
        placeholder="按昵称、系统 ID 或用户文档 ID 搜索"
        @keyup.enter="search"
      />
      <button class="btn btn-primary" :disabled="loading" @click="search">搜索</button>
      <button v-if="isSearching" class="btn" :disabled="loading" @click="clearSearch">清空</button>
    </div>
    <p class="muted search-note">系统 ID 用于线下沟通和管理员搜索；昵称允许重复，不能作为唯一身份。</p>
  </section>

  <p v-if="error" class="notice notice-error" style="margin: 14px 0">{{ error }}</p>
  <div v-if="loading && !users.length" class="state">正在加载用户…</div>
  <div v-else-if="!users.length" class="state">{{ isSearching ? '没有匹配的用户' : '暂无注册用户' }}</div>

  <section v-else class="card user-card">
    <div class="user-list-head">
      <span>用户</span>
      <span>身份与资料</span>
      <span>店铺关联</span>
      <span class="right">操作</span>
    </div>
    <div v-for="user in users" :key="user.id" class="user-row">
      <div class="user-main">
        <img v-if="user.avatarUrl" class="avatar user-avatar" :src="user.avatarUrl" alt="" />
        <span v-else class="avatar avatar-fallback user-avatar">{{ avatarText(user) }}</span>
        <div class="user-copy">
          <span class="user-name">{{ user.nickname }}</span>
          <span class="user-id num">ID {{ user.systemId || '未生成' }}</span>
        </div>
      </div>
      <div class="user-status">
        <span class="badge" :class="user.enabled ? 'badge-on' : 'badge-off'">{{ user.enabled ? '正常' : '已停用' }}</span>
        <span class="muted small">{{ roleText(user.role) }} · {{ user.profileCompleted ? '资料已完善' : '资料未完善' }}</span>
      </div>
      <div class="user-shops">
        <span class="muted small">关联 {{ user.shopCount }} 店</span>
        <span class="muted small">一级 {{ user.ownerCount }} / 二级 {{ user.staffCount }}</span>
      </div>
      <div class="user-actions">
        <button
          class="btn btn-sm"
          :class="user.enabled ? 'btn-danger' : 'btn-primary'"
          :disabled="busyId === user.id || user.role === 'super_admin'"
          @click="toggleUser(user)"
        >
          {{ busyId === user.id ? '处理中…' : (user.enabled ? '停用' : '启用') }}
        </button>
        <button class="btn btn-sm" :disabled="busyId === user.id" @click="resetUserProfile(user)">
          {{ busyId === user.id ? '处理中…' : '重置资料' }}
        </button>
      </div>
    </div>
  </section>

  <div v-if="hasMore && !isSearching" class="load-more">
    <button class="btn" :disabled="loading" @click="loadMore">{{ loading ? '加载中…' : '加载更多' }}</button>
  </div>

  <transition name="toast">
    <div v-if="toast" class="toast">{{ toast }}</div>
  </transition>
</template>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-eyebrow { font-size: 12.5px; color: var(--muted); }
.page-title { font-size: 20px; font-weight: 680; margin-top: 3px; }
.search-card { padding: 16px; }
.search-main { display: flex; gap: 10px; }
.search-main .input { flex: 1; }
.search-note { margin-top: 8px; font-size: 12.5px; }
.user-card { overflow: hidden; margin-top: 14px; }
.user-list-head { display: grid; grid-template-columns: minmax(220px, 1.4fr) minmax(170px, 1fr) minmax(150px, .8fr) 180px; gap: 14px; padding: 10px 16px; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 12px; font-weight: 650; }
.user-list-head .right { text-align: right; }
.user-row { display: grid; grid-template-columns: minmax(220px, 1.4fr) minmax(170px, 1fr) minmax(150px, .8fr) 180px; gap: 14px; align-items: center; padding: 13px 16px; }
.user-row + .user-row { border-top: 1px solid var(--line); }
.user-main { min-width: 0; display: flex; align-items: center; gap: 12px; }
.user-avatar { width: 38px; height: 38px; }
.user-copy, .user-status, .user-shops { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.user-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 600; }
.user-id, .small { font-size: 12px; }
.user-actions { display: flex; justify-content: flex-end; gap: 8px; }
.load-more { display: flex; justify-content: center; padding: 18px 0 0; }
.toast { position: fixed; left: 50%; bottom: 32px; z-index: 60; padding: 11px 18px; border-radius: 100px; background: var(--ink); color: #fff; font-size: 13.5px; box-shadow: 0 8px 24px rgba(20, 28, 24, 0.25); transform: translateX(-50%); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.25s, transform 0.25s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 8px); }
@media (max-width: 860px) { .search-main { flex-direction: column; } .user-list-head { display: none; } .user-row { grid-template-columns: 1fr; gap: 10px; align-items: stretch; } .user-actions { justify-content: flex-start; } }
</style>
