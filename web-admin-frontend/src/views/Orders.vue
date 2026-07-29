<script setup>
import { computed, onMounted, ref } from 'vue';
import { callApi } from '../api.js';

const PAGE_SIZE = 20;
const loading = ref(true);
const loadingShops = ref(true);
const loadingDetail = ref(false);
const exporting = ref(false);
const error = ref('');
const warning = ref('');
const shops = ref([]);
const orders = ref([]);
const total = ref(0);
const hasMore = ref(false);
const page = ref(1);
const detail = ref(null);

const today = getChinaDateKey();
const filters = ref({
  shopId: '',
  status: '',
  dateStart: shiftDate(today, -6),
  dateEnd: today,
});
const activeRange = ref('7');

const rangeLabel = computed(() => `${filters.value.dateStart} 至 ${filters.value.dateEnd}（北京时间）`);
const money = (value) => `¥${Number(value || 0).toFixed(2)}`;

function getChinaDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function shiftDate(dateKey, days) {
  const date = new Date(`${dateKey}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function statusClass(status) {
  if (status === '已完成') return 'badge-on';
  if (status === '已取消') return 'badge-off';
  return 'badge-making';
}

function channelText(channel) {
  return channel === 'table' ? '桌码下单' : '店铺入口下单';
}

async function loadShops() {
  loadingShops.value = true;
  const result = await callApi('listShops');
  loadingShops.value = false;
  if (result.ok) shops.value = result.shops || [];
}

async function load({ reset = false } = {}) {
  if (reset) page.value = 1;
  loading.value = true;
  error.value = '';
  warning.value = '';
  const result = await callApi('listPlatformOrders', {
    ...filters.value,
    page: page.value,
    pageSize: PAGE_SIZE,
  });
  loading.value = false;
  if (!result.ok) {
    error.value = result.message || '订单加载失败';
    return;
  }
  orders.value = reset || page.value === 1 ? result.orders || [] : [...orders.value, ...(result.orders || [])];
  total.value = Number(result.total || 0);
  hasMore.value = result.hasMore === true;
  if (result.truncated) warning.value = '当前日期范围订单较多，仅展示前 5000 条数据。请缩小日期范围查看完整结果。';
}

function setRange(days) {
  activeRange.value = String(days);
  filters.value.dateEnd = today;
  filters.value.dateStart = shiftDate(today, -(days - 1));
  load({ reset: true });
}

function useCustomRange() {
  activeRange.value = 'custom';
}

function applyFilters() {
  activeRange.value = 'custom';
  load({ reset: true });
}

async function loadMore() {
  if (loading.value || !hasMore.value) return;
  page.value += 1;
  await load();
}

async function openDetail(order) {
  loadingDetail.value = true;
  detail.value = { ...order, items: [] };
  const result = await callApi('getPlatformOrderDetail', { recordId: order.recordId });
  loadingDetail.value = false;
  if (result.ok) detail.value = result.order;
  else {
    detail.value = null;
    error.value = result.message || '订单详情加载失败';
  }
}

function closeDetail() {
  if (!loadingDetail.value) detail.value = null;
}

function csvCell(value) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

async function exportOrders() {
  exporting.value = true;
  error.value = '';
  const result = await callApi('exportPlatformOrders', filters.value);
  exporting.value = false;
  if (!result.ok) { error.value = result.message || '订单导出失败'; return; }
  const header = ['订单号', '下单时间', '店铺', '桌位', '下单渠道', '状态', '菜品', '规格', '单价', '数量', '订单总额', '备注'];
  const body = (result.rows || []).map((row) => [row.orderId, row.createdAt, row.shopName, row.tableName, row.channel, row.status, row.dishName, row.options, row.price, row.quantity, row.total, row.remark].map(csvCell).join(','));
  const blob = new Blob([`\uFEFF${header.map(csvCell).join(',')}\n${body.join('\n')}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `平台订单_${result.dateStart}_${result.dateEnd}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  if (result.truncated) warning.value = '导出数据达到 5000 笔订单上限，请缩小日期范围后重新导出。';
}

onMounted(async () => {
  await Promise.all([loadShops(), load({ reset: true })]);
});
</script>

<template>
  <div class="spread page-head">
    <div>
      <p class="page-eyebrow">平台订单只读监管</p>
      <h2 class="page-title">跨店订单</h2>
    </div>
    <div class="row">
      <button class="btn btn-sm" :disabled="exporting" @click="exportOrders">{{ exporting ? '导出中…' : '导出 CSV' }}</button>
      <button class="btn btn-sm" :disabled="loading" @click="load({ reset: true })">{{ loading ? '刷新中…' : '刷新' }}</button>
    </div>
  </div>

  <section class="card filters-card">
    <div class="range-row" aria-label="快捷时间范围">
      <button class="range-btn" :class="{ active: activeRange === '1' }" @click="setRange(1)">今天</button>
      <button class="range-btn" :class="{ active: activeRange === '7' }" @click="setRange(7)">近 7 天</button>
      <button class="range-btn" :class="{ active: activeRange === '30' }" @click="setRange(30)">近 30 天</button>
    </div>
    <div class="filter-grid">
      <label class="field">
        <span>开始日期</span>
        <input v-model="filters.dateStart" class="input" type="date" @change="useCustomRange" />
      </label>
      <label class="field">
        <span>结束日期</span>
        <input v-model="filters.dateEnd" class="input" type="date" @change="useCustomRange" />
      </label>
      <label class="field">
        <span>店铺</span>
        <select v-model="filters.shopId" class="input" :disabled="loadingShops">
          <option value="">全部店铺</option>
          <option v-for="shop in shops" :key="shop.id" :value="shop.id">{{ shop.name }}</option>
        </select>
      </label>
      <label class="field">
        <span>订单状态</span>
        <select v-model="filters.status" class="input">
          <option value="">全部状态</option>
          <option value="制作中">制作中</option>
          <option value="已完成">已完成</option>
          <option value="已取消">已取消</option>
        </select>
      </label>
      <button class="btn btn-primary filter-submit" :disabled="loading" @click="applyFilters">查询订单</button>
    </div>
  </section>

  <p v-if="error" class="notice notice-error feedback">{{ error }}</p>
  <p v-if="warning" class="notice notice-warn feedback">{{ warning }}</p>

  <div class="result-head spread">
    <span class="muted result-summary">{{ rangeLabel }} · 共 {{ total }} 笔</span>
  </div>

  <div v-if="loading && !orders.length" class="state">正在读取订单…</div>
  <div v-else-if="!orders.length" class="state">当前筛选条件下没有订单</div>

  <section v-else class="card orders-card">
    <div class="order-list-head">
      <span>订单</span>
      <span>店铺与桌位</span>
      <span>下单时间</span>
      <span>状态</span>
      <span class="right">金额</span>
    </div>
    <button v-for="order in orders" :key="order.recordId" class="order-row" @click="openDetail(order)">
      <span class="order-id num">{{ order.orderId }}</span>
      <span class="order-place">
        <strong>{{ order.shopName }}</strong>
        <small>{{ order.tableName }} · {{ channelText(order.orderChannel) }}</small>
      </span>
      <span class="order-time">{{ order.createdAt }}</span>
      <span><span class="badge" :class="statusClass(order.status)">{{ order.status }}</span></span>
      <span class="order-total num">{{ money(order.total) }}</span>
    </button>
  </section>

  <div v-if="hasMore" class="load-more">
    <button class="btn" :disabled="loading" @click="loadMore">{{ loading ? '加载中…' : '加载更多' }}</button>
  </div>

  <div v-if="detail" class="overlay" @click.self="closeDetail">
    <section class="modal order-modal" role="dialog" aria-modal="true" aria-labelledby="order-detail-title">
      <header class="modal-head spread">
        <div>
          <p class="modal-eyebrow">订单详情</p>
          <h3 id="order-detail-title" class="modal-title num">{{ detail.orderId }}</h3>
        </div>
        <button class="close-btn" aria-label="关闭订单详情" :disabled="loadingDetail" @click="closeDetail">关闭</button>
      </header>
      <div v-if="loadingDetail" class="state">正在读取订单详情…</div>
      <div v-else class="modal-body">
        <div class="detail-meta">
          <div><span>店铺</span><strong>{{ detail.shopName }}</strong></div>
          <div><span>桌位</span><strong>{{ detail.tableName }}</strong></div>
          <div><span>下单时间</span><strong>{{ detail.createdAt }}</strong></div>
          <div><span>状态</span><strong><span class="badge" :class="statusClass(detail.status)">{{ detail.status }}</span></strong></div>
        </div>
        <p v-if="detail.statusNote" class="status-note">{{ detail.statusNote }}</p>
        <section class="detail-section">
          <h4>菜品明细</h4>
          <ul class="item-list">
            <li v-for="item in detail.items" :key="`${item.id}-${item.optionsText}`" class="item-row">
              <div class="item-copy">
                <strong>{{ item.name }}</strong>
                <small v-if="item.optionsText || item.options?.length">{{ item.optionsText || item.options.join('、') }}</small>
              </div>
              <span class="item-qty">×{{ item.quantity }}</span>
              <span class="item-price num">{{ money(item.price) }}</span>
            </li>
          </ul>
        </section>
        <section v-if="detail.remark" class="detail-section remark-section">
          <h4>顾客备注</h4>
          <p>{{ detail.remark }}</p>
        </section>
        <footer class="detail-total"><span>订单合计</span><strong class="num">{{ money(detail.total) }}</strong></footer>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page-head { margin-bottom: 18px; }
.page-eyebrow, .modal-eyebrow { font-size: 12.5px; color: var(--muted); }
.page-title { margin-top: 3px; font-size: 20px; font-weight: 680; }
.filters-card { padding: 16px; }
.range-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.range-btn {
  height: 32px; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: 7px;
  background: var(--surface); color: var(--ink-soft); font: inherit; font-size: 13px; cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.range-btn:hover { background: var(--surface-2); }
.range-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
.filter-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)) auto; gap: 10px; align-items: end; }
.filter-submit { min-width: 96px; }
.feedback { margin-top: 14px; }
.result-head { margin: 18px 0 10px; }
.result-summary { font-size: 13px; }
.orders-card { overflow: hidden; }
.order-list-head, .order-row {
  display: grid; grid-template-columns: minmax(110px, .75fr) minmax(190px, 1.25fr) minmax(155px, 1fr) 88px 100px;
  gap: 14px; align-items: center;
}
.order-list-head { padding: 10px 16px; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 12px; font-weight: 650; }
.order-list-head .right { text-align: right; }
.order-row {
  width: 100%; padding: 13px 16px; border: 0; border-bottom: 1px solid var(--line); background: var(--surface);
  color: var(--ink); text-align: left; font: inherit; cursor: pointer; transition: background 0.15s;
}
.order-row:last-child { border-bottom: 0; }
.order-row:hover { background: #fafbfa; }
.order-row:focus-visible, .range-btn:focus-visible, .close-btn:focus-visible { outline: 3px solid var(--accent-soft); outline-offset: -2px; }
.order-id { font-size: 13px; font-weight: 650; }
.order-place { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.order-place strong, .order-place small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.order-place strong { font-size: 14px; }
.order-place small, .order-time { font-size: 12px; color: var(--muted); }
.order-total { text-align: right; font-size: 14px; font-weight: 650; }
.badge-making { background: var(--warn-soft); color: var(--warn); }
.load-more { display: flex; justify-content: center; padding-top: 18px; }
.order-modal { max-width: 640px; }
.modal-head { padding: 18px 20px; border-bottom: 1px solid var(--line); }
.modal-title { margin-top: 2px; font-size: 16px; font-weight: 650; }
.close-btn { height: 32px; padding: 0 11px; border: 1px solid var(--line-strong); border-radius: 7px; background: var(--surface); color: var(--ink-soft); font: inherit; font-size: 13px; cursor: pointer; }
.close-btn:hover { background: var(--surface-2); }
.modal-body { gap: 18px; }
.detail-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.detail-meta > div { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.detail-meta span { color: var(--muted); font-size: 12px; }
.detail-meta strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13.5px; font-weight: 600; }
.status-note { margin: -4px 0 0; color: var(--muted); font-size: 13px; }
.detail-section h4 { margin: 0 0 8px; font-size: 13.5px; }
.item-list { margin: 0; padding: 0; list-style: none; }
.item-row { display: grid; grid-template-columns: 1fr 42px 78px; gap: 10px; padding: 10px 0; border-top: 1px solid var(--line); }
.item-copy { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.item-copy strong { font-size: 14px; }
.item-copy small { color: var(--muted); font-size: 12px; }
.item-qty { color: var(--muted); font-size: 13px; text-align: center; }
.item-price { font-size: 13px; font-weight: 600; text-align: right; }
.remark-section { padding: 12px; border-radius: var(--radius-sm); background: var(--surface-2); }
.remark-section p { color: var(--ink-soft); font-size: 13px; line-height: 1.65; white-space: pre-wrap; }
.detail-total { display: flex; justify-content: space-between; padding-top: 14px; border-top: 1px solid var(--line); font-size: 14px; }
.detail-total strong { font-size: 18px; }

@media (max-width: 960px) {
  .filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .filter-submit { width: 100%; }
  .orders-card { overflow-x: auto; }
  .order-list-head, .order-row { min-width: 720px; }
}

@media (max-width: 560px) {
  .filter-grid { grid-template-columns: 1fr; }
  .detail-meta { grid-template-columns: 1fr; }
  .order-modal { max-height: calc(100vh - 32px); overflow-y: auto; }
}
</style>
