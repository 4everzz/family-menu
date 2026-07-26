<script setup>
import { ref, onMounted } from 'vue';
import { callApi } from '../api.js';

const loading = ref(true);
const error = ref('');
const shops = ref([]);

const showCreate = ref(false);
const newName = ref('');
const creating = ref(false);
const createError = ref('');
const newCode = ref(null); // 建店成功后一次性展示的店铺码
const busyId = ref('');

async function load() {
  loading.value = true;
  error.value = '';
  const result = await callApi('listShops');
  loading.value = false;
  if (result.ok) shops.value = result.shops;
  else error.value = result.message || '加载失败';
}

function openCreate() {
  newName.value = '';
  createError.value = '';
  newCode.value = null;
  showCreate.value = true;
}

async function createShop() {
  createError.value = '';
  if (!newName.value.trim()) { createError.value = '请输入店铺名称'; return; }
  creating.value = true;
  const result = await callApi('createShop', { name: newName.value.trim() });
  creating.value = false;
  if (result.ok) {
    newCode.value = result.initialShopCode;
    await load();
  } else {
    createError.value = result.message || '创建失败';
  }
}

async function toggleEnabled(shop) {
  busyId.value = shop.id;
  const result = await callApi('setShopEnabled', { shopId: shop.id, enabled: !shop.enabled });
  busyId.value = '';
  if (result.ok) shop.enabled = !shop.enabled;
  else error.value = result.message || '操作失败';
}

// 进入页面时自动加载店铺列表（之前漏了这行，导致一直卡在“正在加载”）
onMounted(load);
</script>

<template>
  <div class="spread page-head">
    <div>
      <p class="page-eyebrow">共 {{ shops.length }} 家店铺</p>
      <h2 class="page-title">店铺管理</h2>
    </div>
    <div class="row">
      <button class="btn btn-sm" @click="load" :disabled="loading">刷新</button>
      <button class="btn btn-primary btn-sm" @click="openCreate">＋ 新建店铺</button>
    </div>
  </div>

  <p v-if="error" class="notice notice-error" style="margin-bottom:14px">{{ error }}</p>
  <div v-if="loading && !shops.length" class="state">正在加载店铺…</div>
  <div v-else-if="!shops.length" class="state">还没有店铺，点击右上角「新建店铺」创建第一家。</div>

  <div v-else class="card">
    <table class="table">
      <thead>
        <tr>
          <th>店铺</th>
          <th>管理员</th>
          <th>状态</th>
          <th style="text-align:right">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="shop in shops" :key="shop.id">
          <td>
            <div class="stack">
              <span class="shop-name">{{ shop.name }}</span>
              <span class="muted shop-mode">{{ shop.orderEntryMode === 'table_required' ? '桌码点餐' : '到店点餐' }}</span>
            </div>
          </td>
          <td>
            <span class="badge badge-owner">一级 {{ shop.ownerCount }}</span>
            <span class="badge badge-staff" style="margin-left:6px">二级 {{ shop.staffCount }}</span>
          </td>
          <td>
            <span class="badge" :class="shop.enabled ? 'badge-on' : 'badge-off'">
              {{ shop.enabled ? '营业中' : '已停用' }}
            </span>
          </td>
          <td style="text-align:right">
            <button
              class="btn btn-sm"
              :class="shop.enabled ? 'btn-danger' : 'btn-primary'"
              :disabled="busyId === shop.id"
              @click="toggleEnabled(shop)"
            >
              {{ busyId === shop.id ? '处理中…' : (shop.enabled ? '停用' : '启用') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- 新建店铺弹窗 -->
  <div v-if="showCreate" class="overlay" @click.self="!creating && (showCreate = false)">
    <div class="modal">
      <div class="modal-head">
        <h3 style="font-size:16px;font-weight:650">新建店铺</h3>
      </div>

      <div v-if="!newCode" class="modal-body">
        <div class="field">
          <label for="sn">店铺名称</label>
          <input id="sn" class="input" v-model="newName" maxlength="20" placeholder="例如：小家饭堂（前门店）" @keyup.enter="createShop" />
        </div>
        <p class="muted" style="font-size:12.5px">建店后请到「管理员授权」把一位微信用户指派为该店的一级管理员，店铺才有人管理。</p>
        <p v-if="createError" class="notice notice-error">{{ createError }}</p>
      </div>

      <div v-else class="modal-body">
        <p class="notice notice-ok">店铺「{{ newName }}」创建成功</p>
        <div class="field">
          <label>初始店铺码（仅此一次显示，请立即保存）</label>
          <div class="code-box num">{{ newCode }}</div>
        </div>
        <p class="muted" style="font-size:12.5px">店铺码用于顾客到店进入点餐。忘记可在小程序店铺设置里重新生成。</p>
      </div>

      <div class="modal-foot">
        <template v-if="!newCode">
          <button class="btn" @click="showCreate = false" :disabled="creating">取消</button>
          <button class="btn btn-primary" @click="createShop" :disabled="creating">{{ creating ? '创建中…' : '创建' }}</button>
        </template>
        <button v-else class="btn btn-primary" @click="showCreate = false">完成</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-head { margin-bottom: 20px; }
.page-eyebrow { font-size: 12.5px; color: var(--muted); }
.page-title { font-size: 20px; font-weight: 680; margin-top: 3px; }
.shop-name { font-weight: 550; font-size: 14px; }
.shop-mode { font-size: 12px; }
.code-box {
  font-size: 22px; font-weight: 700; letter-spacing: 0.14em;
  padding: 12px 16px; text-align: center;
  background: var(--accent-soft); color: var(--accent-ink);
  border-radius: var(--radius-sm);
}
</style>
