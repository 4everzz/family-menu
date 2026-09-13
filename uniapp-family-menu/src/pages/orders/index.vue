<template>
  <view class="orders-page">
    <view class="page-head">
      <view>
        <text class="page-title">我的订单</text>
        <text class="page-copy">查看当前店铺的下单记录</text>
      </view>
      <button v-if="authStore.isLoggedIn && shopStore.hasShop" class="refresh-button" :disabled="loading" @click="loadOrders(true)">刷新</button>
    </view>

    <view v-if="!authStore.isLoggedIn" class="state-card">
      <text class="state-icon">🍽️</text>
      <text class="state-title">登录后查看订单</text>
      <text class="state-copy">登录后可以查看你在当前店铺的订单和处理进度。</text>
      <button class="primary-button" @click="goLogin">去登录</button>
    </view>

    <view v-else-if="!shopStore.hasShop" class="state-card">
      <text class="state-icon">📱</text>
      <text class="state-title">请先进入店铺</text>
      <text class="state-copy">扫描店铺码或桌码后，才能查看对应店铺的订单。</text>
      <button class="primary-button" @click="goMenu">去扫码进入</button>
    </view>

    <view v-else-if="loading && !orders.length" class="state-card compact-state">正在读取订单…</view>

    <view v-else-if="loadError && !orders.length" class="state-card">
      <text class="state-icon">⚠️</text>
      <text class="state-title">订单读取失败</text>
      <text class="state-copy">{{ loadError }}</text>
      <button class="primary-button" :disabled="loading" @click="loadOrders(true)">重新加载</button>
    </view>

    <view v-else-if="orders.length" class="order-list">
      <view v-for="order in orders" :key="order.id || order._id" class="order-card" @click="openOrder(order)">
        <view class="order-head">
          <view class="order-heading">
            <text class="order-id">订单 {{ order.id || order._id }}</text>
            <text class="order-time">{{ order.createdAt }}</text>
          </view>
          <text class="order-status" :class="statusClass(order.status)">{{ order.status || '制作中' }}</text>
        </view>
        <text class="order-summary">{{ order.summary || '菜品明细' }}</text>
        <text v-if="order.tableName" class="order-table">堂食 · {{ order.tableName }}</text>
        <text v-if="order.remark" class="order-remark">备注：{{ order.remark }}</text>
        <view class="order-foot">
          <text class="order-note">{{ order.statusNote || statusHint(order.status) }}</text>
          <text class="order-total">¥{{ money(order.total) }}</text>
        </view>
      </view>
    </view>

    <view v-else class="state-card">
      <text class="state-icon">🧾</text>
      <text class="state-title">暂无订单</text>
      <text class="state-copy">在当前店铺下单后，订单会显示在这里。</text>
      <button class="primary-button" @click="goMenu">去点菜</button>
    </view>

    <view v-if="selectedOrder" class="modal-mask" @click="selectedOrder = null">
      <view class="detail-modal" @click.stop>
        <view class="modal-head">
          <view>
            <text class="modal-title">订单详情</text>
            <text class="modal-id">{{ selectedOrder.id || selectedOrder._id }}</text>
          </view>
          <button class="close-button" @click="selectedOrder = null">×</button>
        </view>
        <view class="detail-list">
          <view v-for="item in selectedOrder.items || []" :key="item.cartKey || item.id" class="detail-row">
            <view class="detail-copy">
              <text class="detail-name">{{ item.name }}</text>
              <text v-if="item.optionsText || item.options?.length" class="detail-options">{{ item.optionsText || item.options.join('、') }}</text>
            </view>
            <text class="detail-quantity">× {{ item.quantity }}</text>
            <text class="detail-price">¥{{ money(Number(item.price || 0) * Number(item.quantity || 0)) }}</text>
          </view>
        </view>
        <view v-if="selectedOrder.remark" class="detail-remark">备注：{{ selectedOrder.remark }}</view>
        <view class="detail-total"><text>订单合计</text><text>¥{{ money(selectedOrder.total) }}</text></view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue';
import { onShow, onPullDownRefresh } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import { useShopStore } from '../../stores/shop';
import { listMyOrders } from '../../services/menu';
import { getGuestSessionId } from '../../utils/entry-code';
import { showError } from '../../utils/format';

const authStore = useAuthStore();
const shopStore = useShopStore();
const orders = ref([]);
const selectedOrder = ref(null);
const loading = ref(false);
const loadError = ref('');
let requestId = 0;

function context() {
  return {
    shopId: shopStore.shopId,
    entryToken: shopStore.context?.entryToken || '',
    guestSessionId: getGuestSessionId(),
  };
}

function money(value) {
  return Number(value || 0).toFixed(2);
}

function statusClass(status) {
  if (status === '已完成') return 'done';
  if (status === '已取消') return 'cancelled';
  return 'making';
}

function statusHint(status) {
  if (status === '已完成') return '订单已完成';
  if (status === '已取消') return '订单已取消';
  return '订单正在制作中';
}

async function loadOrders(force = false) {
  if (!authStore.isLoggedIn || !shopStore.hasShop) return;
  const currentRequest = ++requestId;
  loading.value = true;
  loadError.value = '';
  try {
    const response = await listMyOrders(context(), { force });
    if (!response?.ok) throw new Error(response?.message || '读取订单失败');
    const source = Array.isArray(response.orders) ? response.orders : [];
    const normalized = source.map((order) => {
      const items = (Array.isArray(order.items) ? order.items : []).map((item) => ({
        ...item,
        cartKey: item.cartKey || `${item.id}|${(item.options || []).join('|')}`,
        optionsText: item.optionsText || (item.options || []).join('、'),
      }));
      return {
        ...order,
        items,
        summary: order.summaryWithOptions || order.summary || items.map((item) => `${item.name} × ${item.quantity}`).join('、'),
        createdAt: formatDate(order.createdAtServer || order.createdAt),
      };
    });
    if (currentRequest === requestId) orders.value = normalized;
  } catch (error) {
    if (currentRequest === requestId) {
      loadError.value = error.message || '暂时无法读取订单';
      if (!orders.value.length) showError(loadError.value);
    }
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function formatDate(value) {
  if (!value) return '';
  const seconds = value && typeof value === 'object' ? (value.seconds ?? value._seconds) : null;
  const raw = Number.isFinite(Number(seconds)) ? Number(seconds) * 1000 : (value?.$date || value);
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return '';
  const chinaDate = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  const pad = (number) => String(number).padStart(2, '0');
  return `${chinaDate.getUTCFullYear()}-${pad(chinaDate.getUTCMonth() + 1)}-${pad(chinaDate.getUTCDate())} ${pad(chinaDate.getUTCHours())}:${pad(chinaDate.getUTCMinutes())}`;
}

function goLogin() {
  uni.navigateTo({ url: '/pages/auth/index?returnTo=/pages/orders/index' });
}

function goMenu() {
  uni.switchTab({ url: '/pages/menu/index' });
}

function openOrder(order) {
  selectedOrder.value = order;
}

onShow(async () => {
  authStore.restore();
  await loadOrders(false);
});

onPullDownRefresh(async () => {
  await loadOrders(true);
  uni.stopPullDownRefresh();
});
</script>

<style scoped>
.orders-page { min-height: 100vh; padding: 28rpx 24rpx calc(48rpx + env(safe-area-inset-bottom)); box-sizing: border-box; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; margin: 8rpx 4rpx 26rpx; }
.page-title { display: block; color: #450a0a; font-size: 42rpx; font-weight: 800; }
.page-copy { display: block; margin-top: 8rpx; color: #78716c; font-size: 24rpx; }
.refresh-button { width: 108rpx; min-width: 108rpx; height: 64rpx; margin: 0; padding: 0; border: 2rpx solid #fecaca; border-radius: 14rpx; background: #fff; color: #b91c1c; font-size: 24rpx; line-height: 60rpx; }
.state-card { display: flex; flex-direction: column; align-items: center; gap: 14rpx; margin-top: 140rpx; padding: 44rpx 30rpx; border: 2rpx solid #fee2e2; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 20rpx rgba(69, 10, 10, .05); text-align: center; }
.compact-state { color: #78716c; font-size: 28rpx; }
.state-icon { font-size: 60rpx; line-height: 1.2; }
.state-title { color: #450a0a; font-size: 32rpx; font-weight: 700; }
.state-copy { color: #78716c; font-size: 25rpx; line-height: 1.6; }
.primary-button { width: 100%; min-width: 0; height: 84rpx; margin: 12rpx 0 0; padding: 0 20rpx; border-radius: 14rpx; background: #dc2626; color: #fff; font-size: 28rpx; font-weight: 700; line-height: 84rpx; box-sizing: border-box; }
.order-list { display: flex; flex-direction: column; gap: 18rpx; }
.order-card { padding: 24rpx; border: 2rpx solid #fee2e2; border-radius: 20rpx; background: #fff; box-shadow: 0 8rpx 18rpx rgba(69, 10, 10, .05); }
.order-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx; }
.order-heading { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 7rpx; }
.order-id { overflow: hidden; color: #450a0a; font-size: 27rpx; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.order-time { color: #a8a29e; font-size: 22rpx; }
.order-status { flex: 0 0 auto; padding: 7rpx 12rpx; border-radius: 999rpx; font-size: 23rpx; font-weight: 700; }
.order-status.making { background: #ffedd5; color: #c2410c; }.order-status.done { background: #dcfce7; color: #15803d; }.order-status.cancelled { background: #f5f5f4; color: #78716c; }
.order-summary { display: block; margin-top: 20rpx; color: #44403c; font-size: 26rpx; line-height: 1.5; }
.order-table, .order-remark { display: block; margin-top: 9rpx; color: #78716c; font-size: 23rpx; }
.order-foot { display: flex; align-items: flex-end; justify-content: space-between; gap: 16rpx; margin-top: 22rpx; padding-top: 18rpx; border-top: 2rpx solid #fef2f2; }
.order-note { min-width: 0; flex: 1; overflow: hidden; color: #a8a29e; font-size: 22rpx; text-overflow: ellipsis; white-space: nowrap; }
.order-total { color: #dc2626; font-size: 32rpx; font-weight: 800; }
.modal-mask { position: fixed; inset: 0; z-index: 20; display: flex; align-items: flex-end; padding: 24rpx 24rpx calc(24rpx + env(safe-area-inset-bottom)); background: rgba(28, 25, 23, .48); box-sizing: border-box; }
.detail-modal { width: 100%; max-height: 78vh; overflow-y: auto; padding: 28rpx; border-radius: 24rpx; background: #fff; box-sizing: border-box; }
.modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20rpx; }.modal-title { display: block; color: #450a0a; font-size: 34rpx; font-weight: 800; }.modal-id { display: block; margin-top: 7rpx; color: #a8a29e; font-size: 22rpx; }
.close-button { width: 60rpx; min-width: 60rpx; height: 60rpx; margin: 0; padding: 0; border-radius: 30rpx; background: #fee2e2; color: #b91c1c; font-size: 38rpx; line-height: 56rpx; }
.detail-list { margin-top: 22rpx; }.detail-row { display: flex; align-items: center; gap: 12rpx; padding: 16rpx 0; border-top: 2rpx solid #fef2f2; }.detail-copy { min-width: 0; flex: 1; }.detail-name { display: block; overflow: hidden; color: #450a0a; font-size: 27rpx; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }.detail-options { display: block; margin-top: 6rpx; color: #78716c; font-size: 22rpx; }.detail-quantity { flex: 0 0 auto; color: #78716c; font-size: 23rpx; }.detail-price { flex: 0 0 auto; min-width: 110rpx; color: #dc2626; font-size: 25rpx; font-weight: 700; text-align: right; }.detail-remark { margin-top: 14rpx; padding: 16rpx; border-radius: 12rpx; background: #fff7ed; color: #7c2d12; font-size: 24rpx; line-height: 1.5; }.detail-total { display: flex; justify-content: space-between; margin-top: 22rpx; padding-top: 20rpx; border-top: 2rpx solid #fecaca; color: #450a0a; font-size: 28rpx; font-weight: 700; }.detail-total text:last-child { color: #dc2626; font-size: 34rpx; }
</style>
