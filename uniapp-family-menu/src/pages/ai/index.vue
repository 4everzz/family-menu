<template>
  <view class="ai-page">
    <view class="hero">
      <view class="hero-badge">AI</view>
      <text class="hero-title">AI 助手</text>
      <text class="hero-copy">拍张照，帮你估算这道菜的热量，点一下就能存进记录。</text>
    </view>

    <!--
      拍照识别热量：从健康档案页整体搬到这里（用户定的归属）。
      识别是 AI 能力，档案页只留手动记一笔。
    -->
    <view class="card">
      <text class="card-title">拍照识别热量</text>
      <text class="card-desc">拍照或从相册选一张，自动识别食物并估算热量</text>

      <view class="recognize-btn" :class="{ disabled: busy }" hover-class="tap" @click="onRecognize">
        {{ busy ? '识别中…' : '拍照 / 从相册选择' }}
      </view>

      <view v-if="mock" class="mock-hint">
        演示数据：把可用的 DashScope Key 填进后端 .env 即自动接通真实识别
      </view>

      <!-- 识别结果：每条「计入热量」一键写进当天记录 -->
      <view v-for="(item, idx) in estimates" :key="idx" class="estimate">
        <view class="estimate-main">
          <text class="estimate-name">{{ item.food_name }}</text>
          <text class="estimate-meta">
            {{ Math.round(item.calories) }} kcal{{ item.portion ? ' · ' + item.portion : '' }}
          </text>
        </view>
        <view
          class="estimate-add"
          :class="{ added: addedMap[idx] }"
          hover-class="tap"
          @click="logEstimate(item, idx)"
        >{{ addedMap[idx] ? '已计入' : '计入热量' }}</view>
      </view>

      <view v-if="todayCount > 0" class="today-sum">
        今天已记 {{ todayCount }} 条 · 合计 {{ Math.round(todayTotal) }} kcal
      </view>
    </view>

    <!-- 后续阶段：对话式推荐（尚未开发） -->
    <view class="plan-card">
      <text class="plan-title">接下来会做</text>
      <view v-for="item in plans" :key="item" class="plan-row">
        <view class="plan-dot" />
        <text class="plan-text">{{ item }}</text>
      </view>
    </view>

    <text class="page-note">其余能力开发中，敬请期待</text>
  </view>
</template>

<script setup lang="ts">
/**
 * AI 助手 tab。
 *
 * 这一栏现在落地的是「拍照识别热量」——它原本做在个人健康档案页，
 * 但识图属于 AI 能力，用户决定整体归到这里（档案页只保留手动记热量）。
 * 识别结果的「一键计入热量」交互保留：识别出食物后点一下就写进当天记录，
 * 不用再手抄数字。
 *
 * 后端接口都已就绪（services/health.ts）：
 *   · recognizeFood  → POST /vision/recognize-food（先 uploadImage 拿相对路径）
 *   · addCalorieLog  → POST /users/me/calorie-logs
 * 身份由后端从令牌解析，前端不传 user_id。
 *
 * 对话式推荐（按冰箱推荐、按减脂条件筛菜…）属后续阶段，暂列在页尾。
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

// 对话式推荐等后续能力，先列出来让用户知道这一栏的规划
const plans = [
  '按家庭冰箱里现有的食材，推荐能做什么菜',
  '按减脂期、低糖、忌口等条件筛选菜品',
  '按人数、口味和预算搭配一桌菜',
];

const busy = ref(false);
const mock = ref(false);
const estimates = ref<FoodEstimate[]>([]);
/** 最近一次识别用的图片相对路径，计入时随记录一起存 */
const lastImageUrl = ref<string | null>(null);
/** 哪几条结果已经计入了（按下标标记），避免重复计入 */
const addedMap = ref<Record<number, boolean>>({});

// 当天记录：用来显示"今天已记 N 条 / 合计 X kcal"，让"计入"有反馈
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

/* 头部：这一栏的品牌感，同时说清"现在能做什么" */
.hero {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-2);
  padding: var(--s-5) var(--s-3);
  border-radius: var(--r-lg);
  background: var(--c-primary-bg);
  border: 2rpx solid var(--c-border);
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  height: 48rpx;
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 22rpx;
}
.hero-title { color: var(--c-text); font-size: 44rpx; font-weight: 500; }
.hero-copy { color: var(--c-text-2); font-size: 25rpx; line-height: 1.7; }

/* 功能卡 */
.card {
  margin-top: var(--s-3);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.card-title { display: block; color: var(--c-text); font-size: 32rpx; font-weight: 500; }
.card-desc { display: block; margin-top: 6rpx; color: var(--c-text-2); font-size: 24rpx; line-height: 1.6; }

.recognize-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 88rpx;
  margin-top: var(--s-3);
  border-radius: var(--r-lg);
  background: var(--c-primary);
  color: #fff;
  font-size: 29rpx;
}
.recognize-btn.disabled { background: var(--c-muted); color: var(--c-text-3); }

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

/* 识别结果行 */
.estimate {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
}
.estimate-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.estimate-name { color: var(--c-text); font-size: 28rpx; font-weight: 500; }
.estimate-meta { color: var(--c-text-2); font-size: 24rpx; }
.estimate-add {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 25rpx;
}
/* 已计入：置灰、"已计入"，防止同一张图重复记两遍 */
.estimate-add.added { background: var(--c-muted); color: var(--c-text-3); }

.today-sum {
  margin-top: var(--s-3);
  color: var(--c-text-2);
  font-size: 23rpx;
  text-align: center;
}

/* 后续规划 */
.plan-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-3);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.plan-title { color: var(--c-text-2); font-size: 23rpx; }
.plan-row { display: flex; align-items: flex-start; gap: var(--s-2); }
/* 用一个小圆点做项目符号，比文字里的「·」对齐更稳，换行时也不会缩进错位 */
.plan-dot {
  flex: 0 0 auto;
  width: 12rpx;
  height: 12rpx;
  margin-top: 14rpx;
  border-radius: 50%;
  background: var(--c-primary);
}
.plan-text { min-width: 0; flex: 1; color: var(--c-text); font-size: 26rpx; line-height: 1.7; }

.page-note {
  display: block;
  margin-top: var(--s-5);
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: center;
}
</style>
