<script setup>
import { computed, onMounted, ref } from 'vue';
import { callApi } from '../api.js';

const loading = ref(true);
const error = ref('');
const shops = ref([]);
const report = ref(null);
const today = getChinaDateKey();
const filters = ref({ shopId: '', dateStart: shiftDate(today, -6), dateEnd: today });
const activeRange = ref('7');
const money = (value) => `¥${Number(value || 0).toFixed(2)}`;
const maxDailyRevenue = computed(() => Math.max(...(report.value?.daily || []).map((item) => Number(item.revenue)), 1));

function getChinaDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}
function shiftDate(key, days) { const date = new Date(`${key}T00:00:00.000Z`); date.setUTCDate(date.getUTCDate() + days); return date.toISOString().slice(0, 10); }
async function loadShops() { const result = await callApi('listShops'); if (result.ok) shops.value = result.shops || []; }
async function load() { loading.value = true; error.value = ''; const result = await callApi('getPlatformReport', filters.value); loading.value = false; if (result.ok) report.value = result.report; else error.value = result.message || '报表加载失败'; }
function setRange(days) { activeRange.value = String(days); filters.value.dateEnd = today; filters.value.dateStart = shiftDate(today, -(days - 1)); load(); }
function customRange() { activeRange.value = 'custom'; }
onMounted(async () => { await Promise.all([loadShops(), load()]); });
</script>

<template>
  <div class="spread page-head"><div><p class="page-eyebrow">订单数据按北京时间汇总</p><h2 class="page-title">经营报表</h2></div><button class="btn btn-sm" :disabled="loading" @click="load">{{ loading ? '刷新中…' : '刷新' }}</button></div>
  <section class="card filters"><div class="range-row"><button class="range-btn" :class="{ active: activeRange === '7' }" @click="setRange(7)">近 7 天</button><button class="range-btn" :class="{ active: activeRange === '30' }" @click="setRange(30)">近 30 天</button></div><div class="filter-grid"><label class="field"><span>开始日期</span><input v-model="filters.dateStart" class="input" type="date" @change="customRange" /></label><label class="field"><span>结束日期</span><input v-model="filters.dateEnd" class="input" type="date" @change="customRange" /></label><label class="field"><span>店铺</span><select v-model="filters.shopId" class="input"><option value="">全部店铺</option><option v-for="shop in shops" :key="shop.id" :value="shop.id">{{ shop.name }}</option></select></label><button class="btn btn-primary filter-submit" :disabled="loading" @click="load">查询报表</button></div></section>
  <p v-if="error" class="notice notice-error feedback">{{ error }}</p><div v-if="loading && !report" class="state">正在汇总订单数据…</div>
  <template v-if="report"><section class="metrics"><div class="metric lead"><span>营业额</span><strong class="num">{{ money(report.revenue) }}</strong><small>{{ report.dateStart }} 至 {{ report.dateEnd }} · 仅已完成订单</small></div><div class="metric"><span>订单数</span><strong class="num">{{ report.orderCount }}</strong><small>制作中 {{ report.makingCount }} · 已完成 {{ report.completedCount }} · 已取消 {{ report.cancelledCount }}</small></div><div class="metric"><span>完成客单价</span><strong class="num">{{ money(report.averageOrderValue) }}</strong><small>已完成营业额 / 已完成订单</small></div></section><div class="cols"><section class="card section"><h3>每日营业额</h3><div v-if="!report.daily.length" class="state">暂无数据</div><div v-for="day in report.daily" :key="day.dateKey" class="daily"><span>{{ day.dateKey.slice(5) }}</span><div class="track"><i :style="{ width: Math.max(2, Number(day.revenue) / maxDailyRevenue * 100) + '%' }"></i></div><strong class="num">{{ money(day.revenue) }}</strong><small>{{ day.orderCount }} 单</small></div></section><section class="card section"><h3>热销菜品</h3><div v-if="!report.topDishes.length" class="state">暂无数据</div><div v-for="(dish, index) in report.topDishes" :key="dish.name" class="rank"><b>{{ index + 1 }}</b><span>{{ dish.name }}</span><strong>{{ dish.quantity }} 份</strong><small class="num">{{ money(dish.revenue) }}</small></div></section></div><section class="card section shops"><h3>店铺业绩排行</h3><div v-if="!report.topShops.length" class="state">暂无数据</div><div v-for="(shop, index) in report.topShops" :key="shop.shopId" class="rank"><b>{{ index + 1 }}</b><span>{{ shop.name }}</span><strong>{{ shop.orderCount }} 单</strong><small class="num">{{ money(shop.revenue) }}</small></div></section></template>
</template>

<style scoped>
.page-head{margin-bottom:18px}.page-eyebrow{font-size:12.5px;color:var(--muted)}.page-title{margin-top:3px;font-size:20px;font-weight:680}.filters,.section{padding:16px}.range-row{display:flex;gap:8px;margin-bottom:14px}.range-btn{height:32px;padding:0 12px;border:1px solid var(--line-strong);border-radius:7px;background:var(--surface);font:inherit;font-size:13px;cursor:pointer}.range-btn.active{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink);font-weight:600}.filter-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;gap:10px;align-items:end}.filter-submit{min-width:96px}.feedback{margin-top:14px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0}.metric{display:flex;flex-direction:column;gap:6px;padding:18px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}.metric span,.metric small{color:var(--muted);font-size:13px}.metric strong{font-size:27px}.lead{background:#234f41;color:#fff;border-color:transparent}.lead span,.lead small{color:rgba(255,255,255,.7)}.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}.section h3{margin:0 0 10px;font-size:15px}.shops{margin-top:16px}.daily{display:grid;grid-template-columns:45px 1fr 82px 35px;gap:8px;align-items:center;padding:9px 0;border-top:1px solid var(--line);font-size:12px}.track{height:7px;border-radius:10px;background:var(--surface-2);overflow:hidden}.track i{display:block;height:100%;border-radius:inherit;background:var(--accent)}.daily strong,.rank small{text-align:right}.daily small{color:var(--muted)}.rank{display:grid;grid-template-columns:28px 1fr 55px 85px;gap:8px;align-items:center;padding:10px 0;border-top:1px solid var(--line);font-size:13px}.rank b{display:flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:6px;background:var(--surface-2);color:var(--muted);font-size:12px}.rank strong{text-align:center;font-weight:600}@media(max-width:760px){.filter-grid,.metrics,.cols{grid-template-columns:1fr}.filter-submit{width:100%}}
</style>
