<template>
  <view class="health-page">
    <!-- 基本信息：性别 / 身高 / 体重 / 目标 -->
    <view class="group">
      <text class="group-title">基本信息</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="pickGender">
          <view class="entry-main">
            <text class="entry-name">性别</text>
            <text class="entry-desc">{{ genderLabel || '未设置' }}</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>

        <view class="entry-item">
          <view class="entry-main">
            <text class="entry-name">身高</text>
          </view>
          <input
            class="field-input"
            v-model="heightInput"
            type="digit"
            placeholder="如 170"
            placeholder-class="field-placeholder"
          />
          <text class="field-unit">cm</text>
        </view>

        <view class="entry-item">
          <view class="entry-main">
            <text class="entry-name">体重</text>
          </view>
          <input
            class="field-input"
            v-model="weightInput"
            type="digit"
            placeholder="如 65"
            placeholder-class="field-placeholder"
          />
          <text class="field-unit">kg</text>
        </view>

        <view class="entry-item" hover-class="tap" @click="pickGoal">
          <view class="entry-main">
            <text class="entry-name">目标</text>
            <text class="entry-desc">{{ goalLabel || '未设置' }}</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 饮食备注：自由文本 -->
    <view class="group">
      <text class="group-title">饮食备注</text>
      <view class="entry-group">
        <textarea
          class="diet-area"
          v-model="diet"
          :maxlength="500"
          placeholder="比如：减脂期 · 清淡饮食 · 忌辛辣、少油少盐"
          placeholder-class="field-placeholder"
        />
        <text class="counter">{{ diet.trim().length }}/500</text>
      </view>
    </view>

    <button
      class="save-btn"
      :class="{ 'save-btn--disabled': saving }"
      :disabled="saving"
      @click="onSave"
    >
      {{ saving ? '保存中…' : '保存档案' }}
    </button>

    <!-- 拍照识别热量 -->
    <view class="group">
      <text class="group-title">拍照识别热量</text>
      <view class="entry-group">
        <button class="photo-btn" :disabled="busy" @click="onRecognize">
          {{ busy ? '识别中…' : '拍照 / 从相册选择' }}
        </button>

        <view v-if="mock" class="mock-hint">演示数据：把可用的 DashScope Key 填进后端 .env 即自动接通真实识别</view>

        <view v-for="(item, idx) in estimates" :key="idx" class="estimate-card">
          <view class="estimate-main">
            <text class="estimate-name">{{ item.food_name }}</text>
            <text class="estimate-kcal">{{ Math.round(item.calories) }} kcal</text>
            <text v-if="item.portion" class="estimate-portion">{{ item.portion }}</text>
          </view>
          <button class="estimate-save" @click="saveEstimate(item)">记下</button>
        </view>
      </view>
    </view>

    <!-- 热量记录：按天分组，算每日合计 -->
    <view class="group">
      <text class="group-title">热量记录</text>
      <view v-if="groupedLogs.length === 0" class="empty-tip">还没有记录，拍张照或手动添加吧</view>

      <view v-for="[day, group] in groupedLogs" :key="day" class="entry-group log-group">
        <view class="log-head">
          <text class="log-date">{{ day }}</text>
          <text class="log-total">当日合计 {{ Math.round(group.total) }} kcal</text>
        </view>
        <view v-for="log in group.items" :key="log.id" class="log-item">
          <image
            v-if="log.image_url"
            class="log-thumb"
            :src="resolveFileUrl(log.image_url)"
            mode="aspectFill"
          />
          <view class="entry-main">
            <text class="entry-name">{{ log.food_name }}</text>
            <text class="entry-desc">{{ Math.round(log.calories) }} kcal{{ log.portion ? ' · ' + log.portion : '' }}</text>
          </view>
          <text class="log-del" hover-class="tap" @click="removeLog(log.id)">删除</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
/**
 * 健康档案页（个人私有域）。
 *
 * 三块能力，都走后端已就绪的接口（services/health.ts）：
 *   · 基本信息 + 饮食备注 —— updateHealthProfile（POST /users/me/health-profile，部分更新）；
 *   · 拍照识别热量 —— chooseImageFromAlbum → uploadImage（拿相对路径）→ recognizeFood；
 *   · 热量记录 —— 列表 / 新增 / 删除，按天汇总显示。
 *
 * 身份完全由后端从令牌解析，前端不传 user_id。没登录时只渲染空态、不发请求。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { resolveFileUrl } from '../../services/http';
import { chooseImageFromAlbum, uploadImage } from '../../services/upload';
import {
  addCalorieLog,
  deleteCalorieLog,
  fetchCalorieLogs,
  fetchHealthProfile,
  recognizeFood,
  updateHealthProfile,
  type CalorieLog,
  type FoodEstimate,
  type Gender,
  type Goal,
  type HealthProfile,
} from '../../services/health';
import { hasValidToken } from '../../utils/token';

// ============ 表单状态 ============
const profile = ref<HealthProfile | null>(null);
const gender = ref<Gender | ''>('');
const heightInput = ref('');
const weightInput = ref('');
const goal = ref<Goal | ''>('');
const diet = ref('');

const saving = ref(false);
const busy = ref(false);

// 识别结果
const estimates = ref<FoodEstimate[]>([]);
const mock = ref(false);
const lastImageUrl = ref<string | null>(null);

// 记录列表
const logs = ref<CalorieLog[]>([]);

const GENDER_OPTIONS: { label: string; value: Gender }[] = [
  { label: '男', value: 'male' },
  { label: '女', value: 'female' },
  { label: '其他', value: 'other' },
];
const GOAL_OPTIONS: { label: string; value: Goal }[] = [
  { label: '减脂', value: 'lose' },
  { label: '维持', value: 'maintain' },
  { label: '增肌', value: 'gain' },
];

const genderLabel = computed(() => GENDER_OPTIONS.find((o) => o.value === gender.value)?.label || '');
const goalLabel = computed(() => GOAL_OPTIONS.find((o) => o.value === goal.value)?.label || '');

/** 按天分组、日期倒序、算每日合计，给列表用 */
const groupedLogs = computed(() => {
  const map = new Map<string, { total: number; items: CalorieLog[] }>();
  for (const log of logs.value) {
    const g = map.get(log.eaten_at) ?? { total: 0, items: [] };
    g.total += log.calories;
    g.items.push(log);
    map.set(log.eaten_at, g);
  }
  return [...map.entries()].sort((a, b) => (a[0] < b[0] ? 1 : -1));
});

// ============ 加载 ============
async function load(): Promise<void> {
  if (!hasValidToken()) return;
  try {
    const p = await fetchHealthProfile();
    profile.value = p;
    if (p) {
      gender.value = (p.gender || '') as Gender | '';
      heightInput.value = p.height_cm != null ? String(p.height_cm) : '';
      weightInput.value = p.weight_kg != null ? String(p.weight_kg) : '';
      goal.value = (p.goal || '') as Goal | '';
      diet.value = p.diet_preferences || '';
    }
    await loadLogs();
  } catch (error) {
    // 拉不到（后端没启动、网络不通）就维持空态，不弹错误干扰浏览
  }
}

async function loadLogs(): Promise<void> {
  if (!hasValidToken()) return;
  try {
    logs.value = await fetchCalorieLogs();
  } catch (error) {
    // 同上，失败不打断页面
  }
}

// ============ 保存档案 ============
async function onSave(): Promise<void> {
  if (saving.value) return;

  const h = parseFloat(heightInput.value);
  const weight = parseFloat(weightInput.value);

  const payload = {
    gender: gender.value || null,
    height_cm: heightInput.value && !Number.isNaN(h) ? h : null,
    weight_kg: weightInput.value && !Number.isNaN(weight) ? weight : null,
    goal: goal.value || null,
    diet_preferences: diet.value.trim() || null,
  };

  saving.value = true;
  try {
    const updated = await updateHealthProfile(payload);
    profile.value = updated;
    uni.showToast({ title: '已保存', icon: 'success' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' });
  } finally {
    saving.value = false;
  }
}

// ============ 选择器 ============
function pickGender(): void {
  uni.showActionSheet({
    itemList: GENDER_OPTIONS.map((o) => o.label),
    success: (res) => {
      gender.value = GENDER_OPTIONS[res.tapIndex].value;
    },
  });
}

function pickGoal(): void {
  uni.showActionSheet({
    itemList: GOAL_OPTIONS.map((o) => o.label),
    success: (res) => {
      goal.value = GOAL_OPTIONS[res.tapIndex].value;
    },
  });
}

// ============ 拍照识别 ============
async function onRecognize(): Promise<void> {
  if (busy.value) return;

  let filePath: string;
  try {
    filePath = await chooseImageFromAlbum();
  } catch (error) {
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
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '识别失败', icon: 'none' });
  } finally {
    busy.value = false;
  }
}

async function saveEstimate(item: FoodEstimate): Promise<void> {
  try {
    await addCalorieLog({
      food_name: item.food_name,
      calories: item.calories,
      portion: item.portion,
      image_url: lastImageUrl.value,
      source: 'vision',
    });
    uni.showToast({ title: '已记录', icon: 'success' });
    estimates.value = [];
    await loadLogs();
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' });
  }
}

// ============ 删除记录 ============
function removeLog(id: number): void {
  uni.showModal({
    title: '删除记录',
    content: '确定删除这条热量记录吗？',
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await deleteCalorieLog(id);
        logs.value = logs.value.filter((l) => l.id !== id);
      } catch (error) {
        uni.showToast({ title: error instanceof Error ? error.message : '删除失败', icon: 'none' });
      }
    },
  });
}

onShow(load);
</script>

<style scoped>
.health-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.group { margin-bottom: var(--s-4); }
.group-title {
  display: block;
  margin: 0 var(--s-1) var(--s-2);
  color: var(--c-text-2);
  font-size: 23rpx;
}

.entry-group {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.entry-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 136rpx;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.entry-item:last-child { border-bottom: none; }
.entry-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.entry-name { color: var(--c-text); font-size: 29rpx; font-weight: 500; }
.entry-desc {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 23rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry-arrow { flex: 0 0 auto; color: var(--c-text-3); font-size: 40rpx; line-height: 1; }

/* 数字输入框：靠右，和单位一起贴在条目的右侧 */
.field-input {
  width: 220rpx;
  text-align: right;
  color: var(--c-text);
  font-size: 29rpx;
}
.field-placeholder { color: var(--c-text-3); }
.field-unit { color: var(--c-text-3); font-size: 24rpx; margin-left: 8rpx; }

/* 饮食备注：占满一行，多行可滚 */
.diet-area {
  width: 100%;
  min-height: 180rpx;
  padding: var(--s-3);
  box-sizing: border-box;
  color: var(--c-text);
  font-size: 27rpx;
  line-height: 1.5;
}
.counter {
  display: block;
  margin: var(--s-1) var(--s-1) 0;
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: right;
}

/* 保存按钮 */
.save-btn {
  margin: var(--s-5) var(--s-1) 0;
  border: none;
  border-radius: var(--r-lg);
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  line-height: 88rpx;
}
.save-btn--disabled { background: var(--c-muted); color: var(--c-text-3); }
.save-btn::after { border: none; }

/* 拍照按钮：和保存按钮同款主色 */
.photo-btn {
  margin: var(--s-3);
  border: none;
  border-radius: var(--r-lg);
  background: var(--c-primary);
  color: #fff;
  font-size: 29rpx;
  line-height: 88rpx;
}
.photo-btn[disabled] { background: var(--c-muted); color: var(--c-text-3); }
.photo-btn::after { border: none; }

/* 占位数据提示 */
.mock-hint {
  margin: 0 var(--s-3) var(--s-3);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-muted);
  color: var(--c-text-2);
  font-size: 22rpx;
  line-height: 1.5;
}

/* 识别结果卡片 */
.estimate-card {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border-top: 2rpx solid var(--c-border);
}
.estimate-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.estimate-name { color: var(--c-text); font-size: 28rpx; font-weight: 500; }
.estimate-kcal { color: var(--c-primary); font-size: 26rpx; }
.estimate-portion { color: var(--c-text-2); font-size: 22rpx; }
.estimate-save {
  flex: 0 0 auto;
  margin: 0;
  padding: 0 var(--s-4);
  border: 2rpx solid var(--c-primary);
  border-radius: var(--r-md);
  background: transparent;
  color: var(--c-primary);
  font-size: 25rpx;
  line-height: 64rpx;
}
.estimate-save::after { border: none; }

/* 记录分组 */
.empty-tip { color: var(--c-text-3); font-size: 25rpx; text-align: center; padding: var(--s-5) 0; }
.log-group { margin-bottom: var(--s-3); }
.log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
  background: var(--c-muted);
}
.log-date { color: var(--c-text); font-size: 26rpx; font-weight: 500; }
.log-total { color: var(--c-text-2); font-size: 24rpx; }
.log-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 120rpx;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.log-item:last-child { border-bottom: none; }
.log-thumb { flex: 0 0 auto; width: 80rpx; height: 80rpx; border-radius: var(--r-sm); background: var(--c-muted); }
.log-del { flex: 0 0 auto; color: var(--c-danger); font-size: 25rpx; padding: 0 var(--s-1); }
</style>
