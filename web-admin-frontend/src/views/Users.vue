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
const restrictions = ref([]);
const restrictionWord = ref('');
const restrictionsLoading = ref(false);
const restrictionBusyId = ref('');

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
  const confirmed = window.confirm(`确定重置「${user.nickname || '该用户'}」的昵称和头像吗？\n\n重置后会生成随机昵称并清空头像，页面将显示昵称首字。系统ID、订单、店铺关系和权限不会受影响；用户重新打开小程序后会收到重新完善资料的提示。`);
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

async function loadRestrictions() {
  restrictionsLoading.value = true;
  const result = await callApi('listNicknameRestrictions');
  restrictionsLoading.value = false;
  if (result.ok) restrictions.value = result.restrictions || [];
  else flash(result.message || '读取限制词失败');
}

async function addRestriction() {
  const word = restrictionWord.value.trim();
  if (!word || restrictionsLoading.value) return;
  restrictionsLoading.value = true;
  const result = await callApi('addNicknameRestriction', { word });
  restrictionsLoading.value = false;
  if (!result.ok) {
    flash(result.message || '添加限制词失败');
    return;
  }
  restrictionWord.value = '';
  await loadRestrictions();
  flash('限制词已添加');
}

async function deleteRestriction(item) {
  if (!item || restrictionBusyId.value) return;
  if (!window.confirm(`确定删除限制词「${item.word}」吗？删除后用户可再次使用包含该词的昵称。`)) return;
  restrictionBusyId.value = item.id;
  const result = await callApi('deleteNicknameRestriction', { id: item.id });
  restrictionBusyId.value = '';
  if (result.ok) {
    restrictions.value = restrictions.value.filter((entry) => entry.id !== item.id);
    flash('限制词已删除');
  } else {
    flash(result.message || '删除限制词失败');
  }
}

onMounted(async () => {
  await Promise.all([load({ reset: true }), loadRestrictions()]);
});
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
        class="input"
        v-model="keyword"
        placeholder="按昵称、系统ID或用户文档ID搜索"
        @keyup.enter="search"
      />
      <button class="btn btn-primary" :disabled="loading" @click="search">搜索</button>
      <button v-if="isSearching" class="btn" :disabled="loading" @click="clearSearch">清空</button>
    </div>
    <p class="muted search-note">系统ID用于线下沟通和管理员搜索；昵称允许重复，不能当唯一身份。</p>
  </section>

  <section class="card restriction-card">
    <div class="restriction-head">
      <div>
        <h3>昵称限制词</h3>
        <p class="muted restriction-note">用户保存资料时，昵称不能包含以下词。匹配会忽略空格和英文大小写。</p>
      </div>
      <button class="btn btn-sm" :disabled="restrictionsLoading" @click="loadRestrictions">{{ restrictionsLoading ? '刷新中…' : '刷新' }}</button>
    </div>
    <div class="restriction-form">
      <input v-model="restrictionWord" class="input" maxlength="12" placeholder="输入 1 至 12 个字符的限制词" @keyup.enter="addRestriction" />
      <button class="btn btn-primary" :disabled="restrictionsLoading || !restrictionWord.trim()" @click="addRestriction">添加</button>
    </div>
    <div v-if="restrictions.length" class="restriction-list">
      <span v-for="item in restrictions" :key="item.id" class="restriction-tag">
        <span>{{ item.word }}</span>
        <button class="restriction-remove" :disabled="restrictionBusyId === item.id" :aria-label="`删除限制词 ${item.word}`" @click="deleteRestriction(item)">{{ restrictionBusyId === item.id ? '…' : '×' }}</button>
      </span>
    </div>
    <p v-else class="muted restriction-empty">暂未设置限制词</p>
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
        <button
          class="btn btn-sm"
          :disabled="busyId === user.id"
          @click="resetUserProfile(user)"
        >
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
.restriction-card { margin-top: 14px; padding: 16px; }
.restriction-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.restriction-head h3 { margin: 0; font-size: 14px; }
.restriction-note, .restriction-empty { margin: 7px 0 0; font-size: 12.5px; line-height: 1.55; }
.restriction-form { display: flex; gap: 10px; margin-top: 14px; }
.restriction-form .input { min-width: 0; flex: 1; }
.restriction-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.restriction-tag { display: inline-flex; align-items: center; gap: 7px; padding: 5px 7px 5px 10px; border: 1px solid var(--line); border-radius: 5px; background: var(--surface-2); color: var(--ink); font-size: 12px; }
.restriction-remove { width: 20px; height: 20px; min-width: 20px; margin: 0; padding: 0; border: 0; border-radius: 3px; background: transparent; color: var(--muted); font-size: 17px; line-height: 18px; box-sizing: border-box; }
.restriction-remove:hover { background: #FEE2E2; color: #B91C1C; }
.restriction-empty { padding: 9px 0 1px; }

.user-card { overflow: hidden; margin-top: 14px; }
.user-list-head {
  display: grid;
  grid-template-columns: minmax(220px, 1.4fr) minmax(170px, 1fr) minmax(150px, .8fr) 180px;
  gap: 14px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}
.user-list-head .right { text-align: right; }
.user-row {
  display: grid;
  grid-template-columns: minmax(220px, 1.4fr) minmax(170px, 1fr) minmax(150px, .8fr) 180px;
  gap: 14px;
  align-items: center;
  padding: 13px 16px;
}
.user-row + .user-row { border-top: 1px solid var(--line); }
.user-main { min-width: 0; display: flex; align-items: center; gap: 12px; }
.user-avatar { width: 38px; height: 38px; }
.user-copy, .user-status, .user-shops { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.user-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; font-weight: 600; }
.user-id, .small { font-size: 12px; }
.user-actions { display: flex; justify-content: flex-end; gap: 8px; }
.load-more { display: flex; justify-content: center; padding: 18px 0 0; }

.toast {
  position: fixed; left: 50%; bottom: 32px; transform: translateX(-50%);
  background: var(--ink); color: #fff;
  padding: 11px 18px; border-radius: 100px;
  font-size: 13.5px; box-shadow: 0 8px 24px rgba(20,28,24,0.25);
  z-index: 60;
}
.toast-enter-active, .toast-leave-active { transition: opacity 0.25s, transform 0.25s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 8px); }

@media (max-width: 860px) {
  .search-main { flex-direction: column; }
  .restriction-form { flex-direction: column; }
  .user-list-head { display: none; }
  .user-row {
    grid-template-columns: 1fr;
    gap: 10px;
    align-items: stretch;
  }
  .user-actions { justify-content: flex-start; }
}
</style>
