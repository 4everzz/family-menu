<script setup>
import { onMounted, ref } from 'vue';
import { callApi } from '../api.js';

const loading = ref(true);
const error = ref('');
const shops = ref([]);

const showCreate = ref(false);
const newName = ref('');
const creating = ref(false);
const createError = ref('');
const newCode = ref(null);
const busyId = ref('');
const rotatingId = ref('');
const toast = ref('');
const qrShop = ref(null);
const renameShop = ref(null);
const renameName = ref('');
const renamePassword = ref('');
const renameError = ref('');
const renaming = ref(false);

async function copyText(text, successText = '已复制') {
  const value = String(text || '').trim();
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    flash(successText);
  } catch (error) {
    flash('复制失败，请手动选中复制');
  }
}

function flash(message) {
  toast.value = message;
  setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2600);
}

function qrImageUrl(code) {
  const content = `SHOP:${String(code || '').trim().toUpperCase()}`;
  return `https://api.qrserver.com/v1/create-qr-code/?size=260x260&margin=16&data=${encodeURIComponent(content)}`;
}

function openQr(shop) {
  if (!shop || !shop.displayShopCode) return;
  qrShop.value = shop;
}

function openRename(shop) {
  if (!shop) return;
  renameShop.value = shop;
  renameName.value = shop.name || '';
  renamePassword.value = '';
  renameError.value = '';
}

function closeRename() {
  if (renaming.value) return;
  renameShop.value = null;
  renameName.value = '';
  renamePassword.value = '';
  renameError.value = '';
}

async function submitRename() {
  const shop = renameShop.value;
  const name = renameName.value.trim();
  if (!shop) return;
  if (!name) {
    renameError.value = '请输入店铺名称';
    return;
  }
  if (name === shop.name) {
    renameError.value = '新店铺名称与当前名称相同';
    return;
  }
  if (!renamePassword.value) {
    renameError.value = '请输入订单删除二级密码';
    return;
  }
  renaming.value = true;
  renameError.value = '';
  const result = await callApi('renameShop', {
    shopId: shop.id,
    name,
    secondaryPassword: renamePassword.value,
  });
  renaming.value = false;
  if (!result.ok) {
    renameError.value = result.message || '修改店铺名称失败';
    return;
  }
  shop.name = result.shop?.name || name;
  closeRename();
  flash('店铺名称已修改');
}

async function load() {
  loading.value = true;
  error.value = '';
  const result = await callApi('listShops');
  loading.value = false;
  if (result.ok) shops.value = result.shops || [];
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
  if (!newName.value.trim()) {
    createError.value = '请输入店铺名称';
    return;
  }
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
  if (result.ok) {
    shop.enabled = !shop.enabled;
    flash(shop.enabled ? '店铺已启用' : '店铺已停用');
  } else {
    error.value = result.message || '操作失败';
  }
}

async function rotateCode(shop) {
  if (!shop || rotatingId.value) return;
  const ok = window.confirm(`确定重置「${shop.name}」的店铺码吗？旧店铺码会立即失效。`);
  if (!ok) return;
  rotatingId.value = shop.id;
  const result = await callApi('rotateShopCode', { shopId: shop.id });
  rotatingId.value = '';
  if (result.ok) {
    shop.displayShopCode = result.shopCode;
    flash('店铺码已重置');
  } else {
    flash(result.message || '重置失败');
  }
}

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

  <div v-else class="card shop-table-card">
    <table class="table">
      <thead>
        <tr>
          <th>店铺</th>
          <th>店铺码</th>
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
            <div v-if="shop.displayShopCode" class="shop-code">
              <button class="code-pill num" @click="copyText(shop.displayShopCode, '已复制店铺码')">{{ shop.displayShopCode }}</button>
              <span class="muted shop-mode">点击可复制</span>
            </div>
            <span v-else class="muted shop-mode">旧码不可查看，请重置后显示</span>
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
          <td>
            <div class="table-actions">
              <button
                class="btn btn-sm"
                :disabled="!shop.displayShopCode"
                @click="openQr(shop)"
              >
                二维码
              </button>
              <button
                class="btn btn-sm"
                :disabled="rotatingId === shop.id"
                @click="rotateCode(shop)"
              >
                {{ rotatingId === shop.id ? '重置中…' : '重置码' }}
              </button>
              <button class="btn btn-sm" @click="openRename(shop)">改名</button>
              <button
                class="btn btn-sm"
                :class="shop.enabled ? 'btn-danger' : 'btn-primary'"
                :disabled="busyId === shop.id"
                @click="toggleEnabled(shop)"
              >
                {{ busyId === shop.id ? '处理中…' : (shop.enabled ? '停用' : '启用') }}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="renameShop" class="overlay" @click.self="closeRename">
    <div class="modal rename-modal" role="dialog" aria-modal="true" aria-labelledby="rename-shop-title">
      <div class="modal-head">
        <p class="muted" style="font-size:12.5px">超级管理员安全操作</p>
        <h3 id="rename-shop-title" style="margin-top:3px;font-size:16px;font-weight:650">修改店铺名称</h3>
      </div>
      <div class="modal-body">
        <p class="muted" style="margin:0;font-size:13px;line-height:1.6">当前名称：{{ renameShop.name }}。Web 后台不限制修改次数，但每次均需验证二级密码。</p>
        <label class="field">
          <span>新店铺名称</span>
          <input v-model="renameName" class="input" maxlength="20" autocomplete="off" @keyup.enter="submitRename" />
        </label>
        <label class="field">
          <span>订单删除二级密码</span>
          <input v-model="renamePassword" class="input" type="password" maxlength="64" autocomplete="current-password" placeholder="输入二级密码后确认修改" @keyup.enter="submitRename" />
        </label>
        <p v-if="renameError" class="notice notice-error">{{ renameError }}</p>
      </div>
      <div class="modal-foot">
        <button class="btn" :disabled="renaming" @click="closeRename">取消</button>
        <button class="btn btn-primary" :disabled="renaming" @click="submitRename">{{ renaming ? '正在修改…' : '确认修改' }}</button>
      </div>
    </div>
  </div>

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
        <p class="muted" style="font-size:12.5px">建店后请到「管理员授权」把一位微信用户指定为该店的一级管理员。</p>
        <p v-if="createError" class="notice notice-error">{{ createError }}</p>
      </div>

      <div v-else class="modal-body">
        <p class="notice notice-ok">店铺「{{ newName }}」创建成功</p>
        <div class="field">
          <label>初始店铺码</label>
          <button class="code-box num" @click="copyText(newCode, '已复制初始店铺码')">{{ newCode }}</button>
        </div>
        <p class="muted" style="font-size:12.5px">店铺码用于顾客到店进入点餐。现在也可以在店铺列表中查看和重置。</p>
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

  <div v-if="qrShop" class="overlay" @click.self="qrShop = null">
    <div class="modal qr-modal">
      <div class="modal-head">
        <h3 style="font-size:16px;font-weight:650">店铺码二维码</h3>
      </div>
      <div class="modal-body qr-body">
        <p class="muted" style="font-size:13px">{{ qrShop.name }}</p>
        <img class="qr-image" :src="qrImageUrl(qrShop.displayShopCode)" alt="店铺码二维码" />
        <div class="code-box num">{{ qrShop.displayShopCode }}</div>
        <p class="muted" style="font-size:12.5px">二维码内容：SHOP:{{ qrShop.displayShopCode }}。顾客用小程序首页扫码即可进入店铺。</p>
      </div>
      <div class="modal-foot">
        <button class="btn" @click="copyText(`SHOP:${qrShop.displayShopCode}`, '已复制二维码内容')">复制二维码内容</button>
        <button class="btn btn-primary" @click="qrShop = null">关闭</button>
      </div>
    </div>
  </div>

  <transition name="toast">
    <div v-if="toast" class="toast">{{ toast }}</div>
  </transition>
</template>

<style scoped>
.page-head { margin-bottom: 20px; }
.page-eyebrow { font-size: 12.5px; color: var(--muted); }
.page-title { font-size: 20px; font-weight: 680; margin-top: 3px; }
.shop-table-card { overflow: hidden; }
.shop-name { font-weight: 550; font-size: 14px; }
.shop-mode { font-size: 12px; }
.shop-code { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.code-pill {
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent-ink);
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.table-actions { display: flex; justify-content: flex-end; gap: 8px; }
.rename-modal { max-width: 460px; }
.code-box {
  width: 100%;
  border: 0;
  font-size: 22px; font-weight: 700; letter-spacing: 0.14em;
  padding: 12px 16px; text-align: center;
  background: var(--accent-soft); color: var(--accent-ink);
  border-radius: var(--radius-sm);
}
.qr-modal { max-width: 420px; }
.qr-body { align-items: center; text-align: center; }
.qr-image {
  width: 260px;
  height: 260px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
}
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
  .shop-table-card { overflow-x: auto; }
  .table { min-width: 850px; }
}
</style>
