<template>
  <view class="ai-page">
    <!--
      页头：和菜单/冰箱页同一套"页面身份"写法（标题 + 一行说明）。
      刻意不用大 banner/徽标——那种"AI 产品落地页"的排场正是要避免的：
      这是一页要用的小工具，不是宣传页。
    -->
    <view class="page-head">
      <text class="page-title">AI 助手</text>
      <text class="page-subtitle">拍照估算热量</text>
    </view>

    <!--
      上传区：整块可点，虚线框 + CSS 相机图标，像个"把照片放进来"的入口，
      而不是一个营销味的大按钮。点下去有按压反馈（hover-class="tap"，全局 0.72 透明度）。
    -->
    <view class="upload-zone" :class="{ busy }" hover-class="tap" @click="onRecognize">
      <view class="zone-glyph" />
      <text class="zone-title">{{ busy ? '识别中…' : '拍照或从相册选择' }}</text>
      <text class="zone-hint">{{ busy ? '正在分析这张照片' : '拍一张食物照片，估算它的热量' }}</text>
    </view>

    <!-- 识别走的是占位数据时如实说明，不假装是真的 -->
    <view v-if="mock" class="mock-hint">
      演示数据：把可用的 DashScope Key 填进后端 .env 即自动接通真实识别
    </view>

    <!-- 识别结果：每条一键计入当天热量记录 -->
    <view v-if="estimates.length" class="section">
      <view class="section-head">
        <text class="section-title">识别结果</text>
        <text class="section-count">{{ estimates.length }} 项</text>
      </view>

      <view v-for="(item, idx) in estimates" :key="idx" class="result">
        <view class="result-main">
          <text class="result-name">{{ item.food_name }}</text>
          <text class="result-meta">
            {{ Math.round(item.calories) }} kcal{{ item.portion ? ' · ' + item.portion : '' }}
          </text>
        </view>
        <!-- 用描边药丸而非实心大按钮：一行一个动作，克制一点，不抢结果的注意力 -->
        <view
          class="result-add"
          :class="{ added: addedMap[idx] }"
          hover-class="tap"
          @click="logEstimate(item, idx)"
        >{{ addedMap[idx] ? '已计入' : '计入热量' }}</view>
      </view>
    </view>

    <!-- 当天累计：给"计入"一个落点，一眼知道今天记了多少 -->
    <view v-if="todayCount > 0" class="today">
      <text class="today-label">今天已记</text>
      <text class="today-value">{{ todayCount }} 条 · {{ Math.round(todayTotal) }} kcal</text>
    </view>
  </view>
</template>

<script setup lang="ts">
/**
 * AI 助手 tab —— 目前落地的是「拍照识别热量」。
 *
 * 这一块原本做在个人健康档案页，但识图属于 AI 能力，用户决定整体归到这里，
 * 档案页只保留手动记热量。识别结果的「一键计入热量」保留：识别出食物后
 * 点一下写进当天记录，不用再手抄数字；同一张图不会重复计入。
 *
 * 后端接口都已就绪（services/health.ts）：
 *   · recognizeFood  → POST /vision/recognize-food（先 uploadImage 拿相对路径）
 *   · addCalorieLog  → POST /users/me/calorie-logs
 * 身份由后端从令牌解析，前端不传 user_id。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import {
  addCalorieLog,
  fetchCalorieLogs,
  recognizeFood,
  type CalorieLog,
  type FoodEstimate,
} from '../../services/health';
import { chooseImageFromAlbum, uploadImage } from '../../services/upload';
import { hasValidToken } from '../../utils/token';

const busy = ref(false);
const mock = ref(false);
const estimates = ref<FoodEstimate[]>([]);
/** 最近一次识别用的图片相对路径，计入时随记录一起存 */
const lastImageUrl = ref<string | null>(null);
/** 哪几条结果已经计入了（按下标标记），避免重复计入 */
const addedMap = ref<Record<number, boolean>>({});

// 当天记录：用来显示"今天已记 N 条 · 合计 X kcal"，让"计入"有反馈
const logs = ref<CalorieLog[]>([]);

/** 本地当天日期 yyyy-mm-dd，和后端记录的 eaten_at 直接比字符串 */
function todayStr(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

const todayLogs = computed(() => logs.value.filter((l) => l.eaten_at === todayStr()));
const todayCount = computed(() => todayLogs.value.length);
const todayTotal = computed(() => todayLogs.value.reduce((sum, l) => sum + l.calories, 0));

async function loadToday(): Promise<void> {
  if (!hasValidToken()) return;
  try {
    logs.value = await fetchCalorieLogs();
  } catch (error) {
    // 拉不到（后端没启动、网络不通）就维持空态，不打断浏览
  }
}

onShow(loadToday);

/**
 * 拍照 / 选图并识别。
 * 先确保登录态：这一串操作都要令牌，没登录时引导去登录页并中止。
 */
async function onRecognize(): Promise<void> {
  if (busy.value) return;
  try {
    await ensureLogin();
  } catch (error) {
    return;
  }

  let filePath: string;
  try {
    filePath = await chooseImageFromAlbum();
  } catch (error) {
    // 用户主动取消选图，静默忽略
    if (error instanceof Error && error.message.includes('cancel')) return;
    uni.showToast({ title: error instanceof Error ? error.message : '选图失败', icon: 'none' });
    return;
  }

  busy.value = true;
  try {
    const result = await uploadImage(filePath);
    const resp = await recognizeFood(result.url);
    mock.value = resp.mock;
    estimates.value = resp.items;
    lastImageUrl.value = result.url;
    addedMap.value = {};
    if (!resp.items.length) {
      uni.showToast({ title: '没识别出食物，换张更清楚的照片试试', icon: 'none' });
    }
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '识别失败', icon: 'none' });
  } finally {
    busy.value = false;
  }
}

/** 一键计入：把这条识别结果写进当天热量记录 */
async function logEstimate(item: FoodEstimate, idx: number): Promise<void> {
  if (addedMap.value[idx]) return;
  try {
    await addCalorieLog({
      food_name: item.food_name,
      calories: item.calories,
      portion: item.portion,
      image_url: lastImageUrl.value,
      source: 'vision',
    });
    addedMap.value = { ...addedMap.value, [idx]: true };
    uni.showToast({ title: '已计入热量', icon: 'success' });
    await loadToday();
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '计入失败', icon: 'none' });
  }
}
</script>

<style scoped>
.ai-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

/* 页头：不加边框和底——它是"页面身份"，不是卡片 */
.page-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}
.page-title {
  overflow: hidden;
  color: var(--c-text);
  font-size: 40rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.page-subtitle { flex: 0 0 auto; color: var(--c-text-2); font-size: 23rpx; }

/* 上传区：虚线框读作"可以往里放东西"，比实心大按钮更像工具而不是广告 */
.upload-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-5) var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
/* 识别中：整体降透明度，示意"先别点"（按钮语义用文字表达，不靠纯颜色） */
.upload-zone.busy { opacity: 0.7; }

/* 相机图标：纯 CSS 拼（机身 + 镜头 + 顶部取景凸起），颜色走主色令牌。
   不用 emoji——跨平台字形不一致、也拿不到设计令牌颜色。 */
.zone-glyph {
  position: relative;
  width: 76rpx;
  height: 60rpx;
  border: 4rpx solid var(--c-primary);
  border-radius: 12rpx;
  box-sizing: border-box;
}
.zone-glyph::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 26rpx;
  height: 26rpx;
  border: 4rpx solid var(--c-primary);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-sizing: border-box;
}
.zone-glyph::after {
  content: '';
  position: absolute;
  left: 16rpx;
  top: -14rpx;
  width: 24rpx;
  height: 12rpx;
  border: 4rpx solid var(--c-primary);
  border-bottom: 0;
  border-radius: 8rpx 8rpx 0 0;
  box-sizing: border-box;
}

.zone-title { color: var(--c-text); font-size: 29rpx; font-weight: 500; }
.zone-hint { color: var(--c-text-2); font-size: 23rpx; }

/* 占位数据提示 */
.mock-hint {
  margin-top: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-muted);
  color: var(--c-text-2);
  font-size: 22rpx;
  line-height: 1.5;
}

.section { margin-top: var(--s-4); }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 0 var(--s-1) var(--s-2);
}
.section-title { color: var(--c-text); font-size: 27rpx; font-weight: 500; }
.section-count { color: var(--c-text-3); font-size: 22rpx; }

.result {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 120rpx;
  margin-bottom: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.result-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.result-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 28rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-meta { color: var(--c-text-2); font-size: 23rpx; }

.result-add {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-primary);
  border-radius: var(--r-pill);
  color: var(--c-primary);
  font-size: 25rpx;
}
/* 已计入：去描边 + 置灰，明确"这条不用再点了" */
.result-add.added {
  border-color: var(--c-border);
  background: var(--c-muted);
  color: var(--c-text-3);
}

/* 当天累计：用主色浅底把它和结果区区分开，但不抢主体 */
.today {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: var(--s-4);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-primary-bg);
}
.today-label { color: var(--c-text-2); font-size: 24rpx; }
.today-value { color: var(--c-primary); font-size: 28rpx; font-weight: 500; }
</style>
