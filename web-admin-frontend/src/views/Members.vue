<script setup>
import { ref, computed, onMounted } from 'vue';
import { callApi } from '../api.js';

const shops = ref([]);
const shopId = ref('');
const loadingShops = ref(true);

const members = ref([]);
const loadingMembers = ref(false);
const membersError = ref('');

const keyword = ref('');
const searching = ref(false);
const searched = ref(false);
const results = ref([]);
const searchError = ref('');

const busyKey = ref('');
const toast = ref('');

const currentShop = computed(() => shops.value.find((s) => s.id === shopId.value) || null);

const roleLabel = (r) => (r === 'store_owner' ? '一级管理员' : r === 'store_staff' ? '二级管理员' : '');

function avatarText(name) { return (name || '·').slice(0, 1).toUpperCase(); }

function flash(msg) { toast.value = msg; setTimeout(() => { if (toast.value === msg) toast.value = ''; }, 2600); }

async function loadShops() {
  loadingShops.value = true;
  const result = await callApi('listShops');
  loadingShops.value = false;
  if (result.ok) {
    shops.value = result.shops;
    if (!shopId.value && shops.value.length) shopId.value = shops.value[0].id;
    if (shopId.value) loadMembers();
  }
}

async function loadMembers() {
  if (!shopId.value) return;
  loadingMembers.value = true;
  membersError.value = '';
  results.value = [];
  searched.value = false;
  keyword.value = '';
  const result = await callApi('listShopMembers', { shopId: shopId.value });
  loadingMembers.value = false;
  if (result.ok) members.value = result.members;
  else { members.value = []; membersError.value = result.message || '加载失败'; }
}

async function search() {
  searchError.value = '';
  if (!keyword.value.trim()) { results.value = []; searched.value = false; return; }
  searching.value = true;
  const result = await callApi('searchUsers', { keyword: keyword.value.trim(), shopId: shopId.value });
  searching.value = false;
  searched.value = true;
  if (result.ok) results.value = result.users;
  else { results.value = []; searchError.value = result.message || '搜索失败'; }
}

async function grant(user, role) {
  busyKey.value = user.id + role;
  const result = await callApi('grantRole', { shopId: shopId.value, userId: user.id, role });
  busyKey.value = '';
  if (result.ok) {
    flash(`已将「${user.nickname}」设为${roleLabel(role)}`);
    user.memberRole = role;
    user.memberRoleText = roleLabel(role);
    await loadMembersKeepSearch();
  } else {
    flash(result.message || '授权失败');
  }
}

async function revoke(target) {
  busyKey.value = (target.userId || target.id) + 'revoke';
  const userId = target.userId || target.id;
  const result = await callApi('revokeRole', { shopId: shopId.value, userId });
  busyKey.value = '';
  if (result.ok) {
    flash('已撤销权限');
    const hit = results.value.find((u) => u.id === userId);
    if (hit) { hit.memberRole = ''; hit.memberRoleText = '未授权'; }
    await loadMembersKeepSearch();
  } else {
    flash(result.message || '撤销失败');
  }
}

// 重新拉成员但不清空当前搜索结果
async function loadMembersKeepSearch() {
  const result = await callApi('listShopMembers', { shopId: shopId.value });
  if (result.ok) members.value = result.members;
}

onMounted(loadShops);
</script>

<template>
  <div class="page-head">
    <p class="page-eyebrow">指派店长与店员</p>
    <h2 class="page-title">管理员授权</h2>
  </div>

  <div v-if="loadingShops" class="state">正在加载店铺…</div>
  <div v-else-if="!shops.length" class="state">还没有店铺，请先到「店铺管理」创建店铺。</div>

  <template v-else>
    <!-- 选择店铺 -->
    <div class="picker card">
      <label class="picker-label">当前店铺</label>
      <select class="input picker-select" v-model="shopId" @change="loadMembers">
        <option v-for="s in shops" :key="s.id" :value="s.id">{{ s.name }}{{ s.enabled ? '' : '（已停用）' }}</option>
      </select>
    </div>

    <div class="cols">
      <!-- 现有管理员 -->
      <section class="card col">
        <div class="col-head spread">
          <h3 class="col-title">现有管理员</h3>
          <span class="muted" style="font-size:12.5px">{{ members.length }} 人</span>
        </div>
        <p v-if="membersError" class="notice notice-error" style="margin:12px">{{ membersError }}</p>
        <div v-if="loadingMembers" class="state">加载中…</div>
        <div v-else-if="!members.length" class="state">这家店还没有管理员</div>
        <ul v-else class="people">
          <li v-for="m in members" :key="m.id" class="person">
            <img v-if="m.avatarUrl" :src="m.avatarUrl" class="avatar" alt="" />
            <span v-else class="avatar avatar-fallback">{{ avatarText(m.nickname) }}</span>
            <div class="person-main">
              <div class="person-top">
                <span class="person-name">{{ m.nickname }}</span>
                <span class="badge" :class="m.role === 'store_owner' ? 'badge-owner' : 'badge-staff'">{{ m.roleText }}</span>
              </div>
              <span class="person-id num">ID {{ m.systemId || '—' }}</span>
            </div>
            <button class="btn btn-danger btn-sm" :disabled="busyKey === m.userId + 'revoke'" @click="revoke(m)">撤销</button>
          </li>
        </ul>
      </section>

      <!-- 搜索并授权 -->
      <section class="card col">
        <div class="col-head">
          <h3 class="col-title">添加管理员</h3>
        </div>
        <div class="search-bar">
          <input
            class="input"
            v-model="keyword"
            placeholder="按昵称或用户ID搜索微信用户"
            @keyup.enter="search"
          />
          <button class="btn btn-primary btn-sm search-go" :disabled="searching" @click="search">
            {{ searching ? '搜索中…' : '搜索' }}
          </button>
        </div>
        <p v-if="searchError" class="notice notice-error" style="margin:0 12px 12px">{{ searchError }}</p>

        <div v-if="!searched" class="state">搜索用户后可将其设为该店的一级 / 二级管理员</div>
        <div v-else-if="!results.length" class="state">没有匹配的用户</div>
        <ul v-else class="people">
          <li v-for="u in results" :key="u.id" class="person">
            <img v-if="u.avatarUrl" :src="u.avatarUrl" class="avatar" alt="" />
            <span v-else class="avatar avatar-fallback">{{ avatarText(u.nickname) }}</span>
            <div class="person-main">
              <div class="person-top">
                <span class="person-name">{{ u.nickname }}</span>
                <span v-if="u.memberRole" class="badge" :class="u.memberRole === 'store_owner' ? 'badge-owner' : 'badge-staff'">{{ u.memberRoleText }}</span>
              </div>
              <span class="person-id num">ID {{ u.systemId || '—' }}</span>
            </div>
            <div class="grant-actions">
              <button class="btn btn-sm" :disabled="busyKey === u.id + 'store_owner' || u.memberRole === 'store_owner'" @click="grant(u, 'store_owner')">设为一级</button>
              <button class="btn btn-sm" :disabled="busyKey === u.id + 'store_staff' || u.memberRole === 'store_staff'" @click="grant(u, 'store_staff')">设为二级</button>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </template>

  <transition name="toast">
    <div v-if="toast" class="toast">{{ toast }}</div>
  </transition>
</template>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-eyebrow { font-size: 12.5px; color: var(--muted); }
.page-title { font-size: 20px; font-weight: 680; margin-top: 3px; }

.picker { display: flex; align-items: center; gap: 14px; padding: 14px 18px; margin-bottom: 16px; }
.picker-label { font-size: 13px; font-weight: 550; color: var(--ink-soft); flex: none; }
.picker-select { max-width: 340px; }

.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
.col { overflow: hidden; }
.col-head { padding: 14px 16px; border-bottom: 1px solid var(--line); }
.col-title { font-size: 14.5px; font-weight: 650; }

.search-bar { display: flex; gap: 8px; padding: 14px 16px; }
.search-go { flex: none; height: 40px; }

.people { list-style: none; margin: 0; padding: 4px 0; }
.person { display: flex; align-items: center; gap: 12px; padding: 11px 16px; }
.person + .person { border-top: 1px solid var(--line); }
.person-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.person-top { display: flex; align-items: center; gap: 8px; }
.person-name { font-size: 14px; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.person-id { font-size: 12px; color: var(--muted); letter-spacing: 0.02em; }
.grant-actions { display: flex; gap: 6px; flex: none; }

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
  .cols { grid-template-columns: 1fr; }
  .grant-actions { flex-direction: column; }
}
</style>
