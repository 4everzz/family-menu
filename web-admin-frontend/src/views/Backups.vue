<script setup>
import { computed, onMounted, ref } from 'vue';
import { callApi } from '../api.js';

const loading = ref(true);
const creating = ref(false);
const error = ref('');
const success = ref('');
const shops = ref([]);
const backups = ref([]);
const today = getChinaDateKey();
const form = ref({ shopId: '', dateStart: shiftDate(today, -30), dateEnd: today });
const selectedShop = computed(() => shops.value.find((shop) => shop.id === form.value.shopId) || null);

function getChinaDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function shiftDate(key, days) {
  const date = new Date(`${key}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function loadShops() {
  const result = await callApi('listShops');
  if (result.ok) {
    shops.value = result.shops || [];
    if (!form.value.shopId && shops.value.length) form.value.shopId = shops.value[0].id;
  } else {
    error.value = result.message || '读取店铺失败';
  }
}

async function loadBackups() {
  loading.value = true;
  const result = await callApi('listShopBackups');
  loading.value = false;
  if (result.ok) backups.value = result.backups || [];
  else error.value = result.message || '读取备份记录失败';
}

async function createBackup() {
  error.value = '';
  success.value = '';
  if (!form.value.shopId) {
    error.value = '请选择需要备份的店铺';
    return;
  }
  creating.value = true;
  const result = await callApi('createShopBackup', form.value);
  creating.value = false;
  if (!result.ok) {
    error.value = result.message || '生成备份失败';
    return;
  }
  success.value = `${selectedShop.value?.name || '店铺'}的备份已生成`;
  await loadBackups();
}

function downloadBackup(backup) {
  if (!backup.downloadUrl) {
    error.value = '下载链接已失效，请刷新备份列表后重试';
    return;
  }
  const link = document.createElement('a');
  link.href = backup.downloadUrl;
  link.download = backup.fileName || 'shop-backup.json';
  link.rel = 'noopener';
  link.click();
}

onMounted(async () => {
  await Promise.all([loadShops(), loadBackups()]);
});
</script>

<template>
  <div class="spread page-head">
    <div>
      <p class="page-eyebrow">订单、菜单与店铺配置的只读备份</p>
      <h2 class="page-title">数据备份</h2>
    </div>
    <button class="btn btn-sm" :disabled="loading" @click="loadBackups">{{ loading ? '刷新中…' : '刷新列表' }}</button>
  </div>

  <section class="card backup-form-card">
    <div class="form-head">
      <div>
        <h3>生成店铺备份</h3>
        <p>保留当前菜品、分类、桌位、店铺设置，以及所选日期内的订单。原数据不会被修改或删除。</p>
      </div>
      <span class="badge badge-on">云存储 JSON</span>
    </div>
    <div class="form-grid">
      <label class="field">
        <span>店铺</span>
        <select v-model="form.shopId" class="input" :disabled="creating || !shops.length">
          <option v-for="shop in shops" :key="shop.id" :value="shop.id">{{ shop.name }}</option>
        </select>
      </label>
      <label class="field">
        <span>订单开始日期</span>
        <input v-model="form.dateStart" class="input" type="date" :disabled="creating" />
      </label>
      <label class="field">
        <span>订单结束日期</span>
        <input v-model="form.dateEnd" class="input" type="date" :disabled="creating" />
      </label>
      <button class="btn btn-primary create-button" :disabled="creating || !shops.length" @click="createBackup">{{ creating ? '正在生成…' : '生成备份' }}</button>
    </div>
    <p class="backup-hint">单次最多备份 31 天、5000 笔订单。菜品图片保留云存储文件编号，不会重复复制图片文件。</p>
  </section>

  <p v-if="error" class="notice notice-error feedback">{{ error }}</p>
  <p v-if="success" class="notice notice-ok feedback">{{ success }}</p>

  <section class="card list-card">
    <div class="list-head"><h3>备份记录</h3><span class="muted">最近 100 份</span></div>
    <div v-if="loading && !backups.length" class="state">正在读取备份记录…</div>
    <div v-else-if="!backups.length" class="state">还没有备份记录</div>
    <div v-else class="backup-list">
      <article v-for="backup in backups" :key="backup.id" class="backup-row">
        <div class="backup-main">
          <strong>{{ backup.shopName }}</strong>
          <span>{{ backup.dateStart }} 至 {{ backup.dateEnd }} · {{ backup.orderCount }} 笔订单 · {{ formatBytes(backup.byteSize) }}</span>
        </div>
        <div class="backup-meta">
          <span>{{ backup.createdAt }}</span>
          <small>创建人：{{ backup.createdBy || '平台管理员' }}</small>
        </div>
        <button class="btn btn-sm" :disabled="!backup.downloadUrl" @click="downloadBackup(backup)">下载 JSON</button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-eyebrow, .muted { color: var(--muted); }
.page-eyebrow { font-size: 12.5px; }
.page-title { margin-top: 3px; font-size: 20px; font-weight: 680; }
.backup-form-card, .list-card { padding: 18px; }
.form-head, .list-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.form-head h3, .list-head h3 { margin: 0; font-size: 15px; }
.form-head p { max-width: 640px; margin: 7px 0 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.form-grid { display: grid; grid-template-columns: minmax(160px, 1.35fr) repeat(2, minmax(140px, 1fr)) auto; gap: 10px; align-items: end; margin-top: 18px; }
.create-button { min-width: 104px; }
.backup-hint { margin: 12px 0 0; color: var(--muted); font-size: 12.5px; line-height: 1.55; }
.feedback { margin: 14px 0; }
.list-card { margin-top: 18px; }
.list-head { align-items: center; margin-bottom: 10px; }
.list-head .muted { font-size: 12.5px; }
.backup-list { border-top: 1px solid var(--line); }
.backup-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(170px, .7fr) auto; gap: 16px; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--line); }
.backup-main, .backup-meta { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.backup-main strong { overflow: hidden; font-size: 14px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.backup-main span, .backup-meta { color: var(--muted); font-size: 12.5px; }
.backup-meta small { font-size: 11.5px; }
@media (max-width: 820px) { .form-grid { grid-template-columns: 1fr 1fr; } .create-button { width: 100%; grid-column: 1 / -1; } .backup-row { grid-template-columns: 1fr auto; } .backup-meta { grid-column: 1; } }
@media (max-width: 520px) { .form-head, .list-head { flex-direction: column; } .form-grid, .backup-row { grid-template-columns: 1fr; } .backup-row .btn { width: 100%; } }
</style>
