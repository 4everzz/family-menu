<script setup>
import { onMounted, ref } from 'vue';
import { callApi } from '../api.js';

const restrictions = ref([]);
const restrictionWord = ref('');
const loading = ref(false);
const busyId = ref('');
const error = ref('');
const notice = ref('');

function flash(message) {
  notice.value = message;
  setTimeout(() => {
    if (notice.value === message) notice.value = '';
  }, 2600);
}

async function loadRestrictions() {
  loading.value = true;
  error.value = '';
  const result = await callApi('listNicknameRestrictions');
  loading.value = false;
  if (result.ok) restrictions.value = result.restrictions || [];
  else error.value = result.message || '读取限制词失败';
}

async function addRestriction() {
  const word = restrictionWord.value.trim();
  if (!word || loading.value) return;
  loading.value = true;
  const result = await callApi('addNicknameRestriction', { word });
  loading.value = false;
  if (!result.ok) {
    error.value = result.message || '添加限制词失败';
    return;
  }
  restrictionWord.value = '';
  await loadRestrictions();
  flash('昵称限制词已添加');
}

async function deleteRestriction(item) {
  if (!item || busyId.value) return;
  if (!window.confirm(`确定删除限制词“${item.word}”吗？删除后用户可再次使用包含该词的昵称。`)) return;
  busyId.value = item.id;
  const result = await callApi('deleteNicknameRestriction', { id: item.id });
  busyId.value = '';
  if (result.ok) {
    restrictions.value = restrictions.value.filter((entry) => entry.id !== item.id);
    flash('昵称限制词已删除');
  } else {
    error.value = result.message || '删除限制词失败';
  }
}

onMounted(loadRestrictions);
</script>

<template>
  <div class="spread page-head">
    <div>
      <p class="page-eyebrow">平台用户资料治理</p>
      <h2 class="page-title">昵称限制词</h2>
    </div>
    <button class="btn btn-sm" :disabled="loading" @click="loadRestrictions">{{ loading ? '刷新中…' : '刷新' }}</button>
  </div>

  <section class="card restriction-card">
    <p class="restriction-copy">用户保存资料时，昵称不得包含限制词；匹配会忽略空格和英文大小写。</p>
    <div class="restriction-form">
      <input v-model="restrictionWord" class="input" maxlength="12" placeholder="输入 1 至 12 个字符的限制词" @keyup.enter="addRestriction" />
      <button class="btn btn-primary" :disabled="loading || !restrictionWord.trim()" @click="addRestriction">添加</button>
    </div>

    <p v-if="error" class="notice notice-error">{{ error }}</p>
    <div v-if="loading && !restrictions.length" class="state">正在读取限制词…</div>
    <div v-else-if="restrictions.length" class="restriction-list">
      <span v-for="item in restrictions" :key="item.id" class="restriction-tag">
        <span>{{ item.word }}</span>
        <button class="restriction-remove" type="button" :disabled="busyId === item.id" :aria-label="`删除限制词 ${item.word}`" @click="deleteRestriction(item)">{{ busyId === item.id ? '…' : '×' }}</button>
      </span>
    </div>
    <p v-else class="muted restriction-empty">暂未设置昵称限制词</p>
  </section>

  <transition name="toast">
    <div v-if="notice" class="toast">{{ notice }}</div>
  </transition>
</template>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-eyebrow { font-size: 12.5px; color: var(--muted); }
.page-title { margin-top: 3px; font-size: 20px; font-weight: 680; }
.restriction-card { padding: 18px; }
.restriction-copy { color: var(--muted); font-size: 13px; line-height: 1.6; }
.restriction-form { display: flex; gap: 10px; margin-top: 16px; }
.restriction-form .input { min-width: 0; flex: 1; }
.notice { margin-top: 14px; }
.restriction-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.restriction-tag { display: inline-flex; align-items: center; gap: 7px; padding: 5px 7px 5px 10px; border: 1px solid var(--line); border-radius: 5px; background: var(--surface-2); color: var(--ink); font-size: 12px; }
.restriction-remove { width: 20px; height: 20px; min-width: 20px; margin: 0; padding: 0; border: 0; border-radius: 3px; background: transparent; color: var(--muted); font-size: 17px; line-height: 18px; box-sizing: border-box; cursor: pointer; }
.restriction-remove:hover { background: var(--danger-soft); color: var(--danger); }
.restriction-empty { padding: 18px 0 2px; font-size: 13px; }
.toast { position: fixed; left: 50%; bottom: 32px; z-index: 60; padding: 11px 18px; border-radius: 100px; background: var(--ink); color: #fff; font-size: 13.5px; box-shadow: 0 8px 24px rgba(20, 28, 24, 0.25); transform: translateX(-50%); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.25s, transform 0.25s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 8px); }
@media (max-width: 640px) { .restriction-form { flex-direction: column; } }
</style>
