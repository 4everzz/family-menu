<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { callApi } from '../api.js';

const loading = ref(true);
const error = ref('');
const data = ref(null);
const router = useRouter();

const money = (n) => '¥' + Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int = (n) => Number(n || 0).toLocaleString('zh-CN');

const maxRevenue = computed(() => {
  const shops = data.value?.topShops || [];
  return shops.reduce((max, s) => Math.max(max, Number(s.revenue) || 0), 0) || 1;
});

async function load() {
  loading.value = true;
  error.value = '';
  const result = await callApi('getPlatformOverview');
  loading.value = false;
  if (result.ok) data.value = result.overview;
  else error.value = result.message || '加载失败';
}

onMounted(load);
</script>

<template>
  <div class="spread page-head">
    <div>
      <p class="page-eyebrow">今日 · {{ data?.dateKey || '——' }}（北京时间）</p>
      <h2 class="page-title">平台经营概览</h2>
    </div>
    <div class="row">
      <button class="btn btn-sm" @click="router.push({ name: 'operations', query: { tab: 'orders' } })">查看订单</button>
      <button class="btn btn-sm" @click="load" :disabled="loading">{{ loading ? '刷新中…' : '刷新' }}</button>
    </div>
  </div>

  <p v-if="error" class="notice notice-error">{{ error }}</p>
  <div v-if="loading && !data" class="state">正在加载平台数据…</div>

  <template v-if="data">
    <!-- 今日跨店三大指标 -->
    <section class="metrics">
      <div class="metric metric-lead">
        <span class="metric-label">今日营业额（全平台）</span>
        <span class="metric-value num">{{ money(data.todayRevenue) }}</span>
        <span class="metric-foot">{{ int(data.todayOrderCount) }} 笔订单 · 已完成 {{ int(data.todayCompletedCount) }} · 已取消 {{ int(data.todayCancelledCount) }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">今日订单</span>
        <span class="metric-value num">{{ int(data.todayOrderCount) }}</span>
        <span class="metric-foot">已完成 {{ int(data.todayCompletedCount) }} · 已取消 {{ int(data.todayCancelledCount) }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">营业中店铺</span>
        <span class="metric-value num">{{ int(data.shopsEnabled) }}<span class="metric-of">/ {{ int(data.shopsTotal) }}</span></span>
        <span class="metric-foot">已停用 {{ int(data.shopsTotal - data.shopsEnabled) }} 家</span>
      </div>
    </section>

    <!-- 平台账户构成 -->
    <section class="mini-row">
      <div class="mini"><span class="mini-n num">{{ int(data.usersTotal) }}</span><span class="mini-l">注册用户</span></div>
      <div class="mini"><span class="mini-n num">{{ int(data.ownerCount) }}</span><span class="mini-l">一级管理员</span></div>
      <div class="mini"><span class="mini-n num">{{ int(data.staffCount) }}</span><span class="mini-l">二级管理员</span></div>
    </section>

    <!-- 今日店铺业绩排行（signature） -->
    <section class="card rank">
      <div class="rank-head spread">
        <h3 class="rank-title">今日店铺业绩</h3>
        <span class="muted rank-sub">按营业额排序 · Top {{ (data.topShops || []).length }}</span>
      </div>

      <div v-if="!(data.topShops && data.topShops.length)" class="state">今天还没有任何订单</div>

      <ol v-else class="rank-list">
        <li v-for="(shop, i) in data.topShops" :key="shop.shopId" class="rank-item">
          <span class="rank-no" :class="{ top: i < 3 }">{{ i + 1 }}</span>
          <div class="rank-main">
            <div class="spread rank-line">
              <span class="rank-name">{{ shop.name }}</span>
              <span class="rank-rev num">{{ money(shop.revenue) }}</span>
            </div>
            <div class="rank-bar">
              <span class="rank-fill" :style="{ width: Math.max(3, (shop.revenue / maxRevenue) * 100) + '%' }"></span>
            </div>
            <span class="rank-orders muted">{{ int(shop.orderCount) }} 笔订单</span>
          </div>
        </li>
      </ol>
    </section>
  </template>
</template>

<style scoped>
.page-head { margin-bottom: 22px; }
.page-eyebrow { font-size: 12.5px; color: var(--muted); letter-spacing: 0.02em; }
.page-title { font-size: 20px; font-weight: 680; letter-spacing: -0.01em; margin-top: 3px; }

.metrics {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.metric {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  box-shadow: var(--shadow-sm);
}
.metric-lead {
  background: linear-gradient(158deg, #234f41 0%, #1d2623 100%);
  border-color: transparent;
}
.metric-lead .metric-label { color: rgba(255,255,255,0.72); }
.metric-lead .metric-value { color: #fff; }
.metric-lead .metric-foot { color: rgba(255,255,255,0.6); }
.metric-label { font-size: 13px; color: var(--muted); font-weight: 500; }
.metric-value { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; }
.metric-of { font-size: 16px; color: var(--muted); font-weight: 500; margin-left: 4px; }
.metric-foot { font-size: 12.5px; color: var(--muted); }

.mini-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 22px; }
.mini {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 18px;
  display: flex; align-items: baseline; gap: 10px;
}
.mini-n { font-size: 20px; font-weight: 700; }
.mini-l { font-size: 13px; color: var(--muted); }

.rank { padding: 6px 4px 10px; }
.rank-head { padding: 14px 18px 10px; }
.rank-title { font-size: 15px; font-weight: 650; }
.rank-sub { font-size: 12.5px; }

.rank-list { list-style: none; margin: 0; padding: 0; }
.rank-item {
  display: flex; gap: 14px; align-items: flex-start;
  padding: 13px 18px;
  border-top: 1px solid var(--line);
}
.rank-no {
  flex: none;
  width: 24px; height: 24px; margin-top: 1px;
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12.5px; font-weight: 700;
  background: var(--surface-2); color: var(--muted);
  font-family: var(--font-num);
}
.rank-no.top { background: var(--accent-soft); color: var(--accent-ink); }
.rank-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.rank-line { gap: 12px; }
.rank-name { font-size: 14px; font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-rev { font-size: 14px; font-weight: 650; }
.rank-bar { height: 6px; border-radius: 100px; background: var(--surface-2); overflow: hidden; }
.rank-fill { display: block; height: 100%; border-radius: 100px; background: linear-gradient(90deg, var(--accent), #4a9a80); }
.rank-orders { font-size: 12px; }

@media (max-width: 720px) {
  .metrics { grid-template-columns: 1fr; }
  .mini-row { grid-template-columns: 1fr; }
}
</style>
