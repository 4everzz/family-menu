<template>
  <view class="health-page">
    <!-- 下拉打开时的透明遮罩：点别处收起。透明不挡视觉，只接住"点空白处关闭" -->
    <view v-if="openPicker" class="picker-mask" @click="closePicker" />

    <!-- 基本信息：性别 / 身高 / 体重 / 目标 -->
    <view class="group">
      <text class="group-title">基本信息</text>
      <view class="entry-group">
        <!--
          性别/目标用**卡片内小下拉**（用户定的交互）：
          点行就在这行下面展开一个小菜单（约卡片 1/3 宽、贴右侧箭头），
          不再弹全屏 ActionSheet——选个性别这种一步操作，不该把整个屏幕都罩住。
        -->
        <view class="entry-item picker-row" hover-class="tap" @click="togglePicker('gender')">
          <view class="entry-main">
            <text class="entry-name">性别</text>
            <text class="entry-desc">{{ genderLabel || '未设置' }}</text>
          </view>
          <text class="entry-arrow">›</text>
          <view v-if="openPicker === 'gender'" class="inline-dropdown" @click.stop>
            <view
              v-for="o in GENDER_OPTIONS"
              :key="o.value"
              class="dropdown-option"
              :class="{ active: gender === o.value }"
              hover-class="tap"
              @click="chooseGender(o)"
            >{{ o.label }}</view>
          </view>
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

        <view class="entry-item picker-row" hover-class="tap" @click="togglePicker('goal')">
          <view class="entry-main">
            <text class="entry-name">目标</text>
            <text class="entry-desc">{{ goalLabel || '未设置' }}</text>
          </view>
          <text class="entry-arrow">›</text>
          <view v-if="openPicker === 'goal'" class="inline-dropdown" @click.stop>
            <view
              v-for="o in GOAL_OPTIONS"
              :key="o.value"
              class="dropdown-option"
              :class="{ active: goal === o.value }"
              hover-class="tap"
              @click="chooseGoal(o)"
            >{{ o.label }}</view>
          </view>
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

    <!--
      拍照识别热量已从本页移除（用户定的）：它后期整体挪到「AI」栏，
      识别结果"一键计入热量"的交互到那时保留。这里先留手动记一笔，
      否则识别挪走后热量记录就没有任何录入途径、整个模块成死页。
    -->

    <!-- 热量记录：按天分组，算每日合计 -->
    <view class="group">
      <text class="group-title">热量记录</text>

      <!-- 手动记一笔：吃了什么 + 多少千卡，一条搞定 -->
      <view class="entry-group manual-add">
        <input
          class="manual-name"
          v-model="newFood"
          placeholder="吃了什么，如 番茄炒蛋"
          placeholder-class="field-placeholder"
        />
        <input
          class="manual-kcal"
          v-model="newKcal"
          type="digit"
          placeholder="kcal"
          placeholder-class="field-placeholder"
        />
        <view class="manual-btn" hover-class="tap" @click="addManual">记一笔</view>
      </view>

      <view v-if="groupedLogs.length === 0" class="empty-tip">还没有记录，在上面记一笔吧</view>

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
 * 能力块，都走后端已就绪的接口（services/health.ts）：
 *   · 基本信息 + 饮食备注 —— updateHealthProfile（POST /users/me/health-profile，部分更新）；
 *   · 热量记录 —— 手动记一笔 / 列表 / 删除，按天汇总显示。
 *
 * 拍照识别热量**不放在这一页**（用户定的）：后期整体挪到「AI」栏去做，
 * 识别结果"一键计入热量"的交互保留到那时的设计里（后端 /vision/recognize-food 不动）。
 *
 * 身份完全由后端从令牌解析，前端不传 user_id。没登录时只渲染空态、不发请求。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { resolveFileUrl } from '../../services/http';
import {
  addCalorieLog,
  deleteCalorieLog,
  fetchCalorieLogs,
  fetchHealthProfile,
  updateHealthProfile,
  type CalorieLog,
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

// ============ 卡片内小下拉 ============
/** 当前展开的下拉：gender / goal，空串表示都没开（同一时间只开一个） */
const openPicker = ref<'gender' | 'goal' | ''>('');

function togglePicker(which: 'gender' | 'goal'): void {
  openPicker.value = openPicker.value === which ? '' : which;
}

function closePicker(): void {
  openPicker.value = '';
}

function chooseGender(o: { label: string; value: Gender }): void {
  gender.value = o.value;
  closePicker();
}

function chooseGoal(o: { label: string; value: Goal }): void {
  goal.value = o.value;
  closePicker();
}

// ============ 手动记一笔 ============
const newFood = ref('');
const newKcal = ref('');

/** 手动记一条热量。校验放在前端做一层（后端还有自己的校验），提示用中文 */
async function addManual(): Promise<void> {
  const name = newFood.value.trim();
  const kcal = parseFloat(newKcal.value);
  if (!name) {
    uni.showToast({ title: '先写吃了什么', icon: 'none' });
    return;
  }
  if (Number.isNaN(kcal) || kcal <= 0) {
    uni.showToast({ title: '热量要填大于 0 的数字', icon: 'none' });
    return;
  }
  try {
    await addCalorieLog({ food_name: name, calories: kcal, source: 'manual' });
    newFood.value = '';
    newKcal.value = '';
    uni.showToast({ title: '已记录', icon: 'success' });
    await loadLogs();
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '记录失败', icon: 'none' });
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

/* 不用 overflow:hidden 裁圆角——性别/目标的小下拉要从卡片里伸出来，
   裁了会被切掉。圆角改由首尾行自己承担 */
.entry-group {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.entry-item:first-child {
  border-top-left-radius: var(--r-lg);
  border-top-right-radius: var(--r-lg);
}
.entry-item:last-child {
  border-bottom-left-radius: var(--r-lg);
  border-bottom-right-radius: var(--r-lg);
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

/* ---------- 卡片内小下拉 ----------
   贴着行右侧箭头往下展开，宽度约卡片 1/3（用户定的）。
   遮罩透明、z-index 20；下拉 30 压在遮罩上，也压住下面的分组。 */
.picker-row { position: relative; }
.picker-mask { position: fixed; inset: 0; z-index: 20; background: transparent; }
.inline-dropdown {
  position: absolute;
  top: calc(100% + 6rpx);
  right: var(--s-3);
  z-index: 30;
  width: 33%;
  min-width: 200rpx;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  box-shadow: var(--shadow-float);
  overflow: hidden;
}
.dropdown-option {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--touch-min);
  color: var(--c-text-2);
  font-size: 26rpx;
}
.dropdown-option + .dropdown-option { border-top: 2rpx solid var(--c-border); }
.dropdown-option.active {
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-weight: 500;
}

/* ---------- 手动记一笔 ---------- */
.manual-add {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-2);
  padding: var(--s-2) var(--s-3);
}
.manual-name { flex: 1; min-width: 0; height: var(--touch-min); color: var(--c-text); font-size: 27rpx; }
.manual-kcal {
  flex: 0 0 140rpx;
  width: 140rpx;
  height: var(--touch-min);
  color: var(--c-text);
  font-size: 27rpx;
  text-align: right;
}
.manual-btn {
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
