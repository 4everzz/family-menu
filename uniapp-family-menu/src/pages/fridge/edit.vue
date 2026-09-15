<template>
  <view class="edit-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <template v-else>
      <view class="form-card">
        <view class="field-group">
          <text class="field-label">食材名（必填）</text>
          <input
            v-model="form.name"
            class="field-input"
            :class="{ focused: focusedField === 'name' }"
            placeholder="例如：鸡蛋"
            placeholder-class="field-placeholder"
            maxlength="64"
            @focus="focusedField = 'name'"
            @blur="focusedField = ''"
          />
        </view>

        <view class="field-group">
          <text class="field-label">数量（必填）</text>
          <view class="qty-row">
            <input
              v-model="form.quantity"
              class="field-input qty-input"
              :class="{ focused: focusedField === 'quantity' }"
              type="digit"
              placeholder="如 10"
              placeholder-class="field-placeholder"
              @focus="focusedField = 'quantity'"
              @blur="focusedField = ''"
            />
            <input
              v-model="form.unit"
              class="field-input qty-unit"
              :class="{ focused: focusedField === 'unit' }"
              placeholder="单位，如 个/盒"
              placeholder-class="field-placeholder"
              maxlength="8"
              @focus="focusedField = 'unit'"
              @blur="focusedField = ''"
            />
          </view>
        </view>

        <view class="field-group">
          <text class="field-label">分类</text>
          <view class="chip-row">
            <view
              v-for="c in CATEGORIES"
              :key="c"
              class="chip"
              :class="{ active: form.category === c }"
              hover-class="tap"
              @click="form.category = c"
            >{{ c }}</view>
          </view>
        </view>

        <view class="field-group">
          <text class="field-label">存放位置</text>
          <view class="chip-row">
            <view
              v-for="s in STORAGES"
              :key="s"
              class="chip"
              :class="{ active: form.storage === s }"
              hover-class="tap"
              @click="form.storage = s"
            >{{ s }}</view>
          </view>
        </view>

        <view class="field-group">
          <text class="field-label">保质期</text>
          <picker mode="date" :value="form.expiryDate" @change="onDateChange">
            <view class="picker" :class="{ placeholder: !form.expiryDate }">
              {{ form.expiryDate || '不选则忽略保质期' }}
            </view>
          </picker>
          <text v-if="form.expiryDate" class="clear-date" hover-class="tap" @click="form.expiryDate = ''">清除</text>
        </view>

        <view class="field-group">
          <view class="field-head">
            <text class="field-label">备注</text>
            <text class="field-count">{{ form.note.length }} / 200</text>
          </view>
          <textarea
            v-model="form.note"
            class="field-textarea"
            :class="{ focused: focusedField === 'note' }"
            maxlength="200"
            placeholder="比如：开封后尽快吃完"
            placeholder-class="field-placeholder"
            @focus="focusedField = 'note'"
            @blur="focusedField = ''"
          />
        </view>
      </view>

      <view class="save-btn" :class="{ disabled: !canSave }" hover-class="tap" @click="submit">
        {{ pending ? '正在保存…' : isEdit ? '保存修改' : '加入冰箱' }}
      </view>

        <view v-if="isEdit" class="delete-btn" hover-class="tap" @click="confirmDelete">删除这件食材</view>

      </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 食材编辑页：新增和编辑共用一个页面（入口都在「家庭冰箱」列表）。
 *
 *   /pages/fridge/edit        → 新增
 *   /pages/fridge/edit?id=12  → 编辑第 12 件食材
 *
 * 权限：只有家庭组创建人能进这个页（列表页的入口按 isOwner 显示）。
 * 这里再校验一次，万一有人绕过界面直接 navigate 进来，后端写接口仍会拦。
 */

import { computed, ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import {
  createFridgeItem,
  fetchFridgeItem,
  updateFridgeItem,
  deleteFridgeItem,
  type FridgeItem,
} from '../../services/fridge';
import { getCurrentSpace, getCurrentSpaceId } from '../../utils/space-context';
import { showError } from '../../utils/format';
import { DANGER } from '../../utils/theme';

const CATEGORIES = ['蔬菜', '肉蛋', '水产', '调料', '饮品', '其他'];
const STORAGES = ['冷藏', '冷冻', '常温'];

const spaceId = ref('');
const itemId = ref('');
const loading = ref(true);
const pending = ref(false);
const focusedField = ref('');

/** 表单内容。reactive 比四个 ref 整齐 */
const form = ref({
  name: '',
  quantity: '' as string,
  unit: '',
  category: '' as string,
  storage: '' as string,
  expiryDate: '' as string,
  note: '',
});

const isEdit = computed(() => !!itemId.value);
/** 食材名必填、数量必填且为正；其余可选 */
const canSave = computed(
  () => !pending.value && !!form.value.name.trim() && isPositiveNumber(form.value.quantity),
);

function isPositiveNumber(value: string): boolean {
  const n = Number(value);
  return Number.isFinite(n) && n > 0;
}

function onDateChange(e: { detail: { value: string } }): void {
  form.value.expiryDate = e.detail.value;
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    await ensureLogin();
    spaceId.value = getCurrentSpaceId();

    if (!spaceId.value) {
      showError('还没有选择家庭组');
      setTimeout(() => uni.navigateBack(), 900);
      return;
    }

    // 非创建人不应进编辑页；后端还会再拦一次
    if (getCurrentSpace()?.myRole !== 'admin') {
      showError('只有创建人能修改冰箱');
      setTimeout(() => uni.navigateBack(), 900);
      return;
    }

    if (isEdit.value) {
      const item: FridgeItem = await fetchFridgeItem(spaceId.value, itemId.value);
      form.value = {
        name: item.name,
        // 数量回显为字符串，输入框才接得住
        quantity: item.quantity % 1 === 0 ? String(item.quantity) : item.quantity.toFixed(1),
        unit: item.unit,
        category: item.category,
        storage: item.storage,
        expiryDate: item.expiryDate || '',
        note: item.note,
      };
      uni.setNavigationBarTitle({ title: '编辑食材' });
    } else {
      uni.setNavigationBarTitle({ title: '新增食材' });
    }
  } catch (error) {
    showError(error);
  } finally {
    loading.value = false;
  }
}

async function submit(): Promise<void> {
  if (!canSave.value) return;
  pending.value = true;
  try {
    const payload = {
      name: form.value.name.trim(),
      quantity: Number(form.value.quantity),
      unit: form.value.unit,
      category: form.value.category,
      storage: form.value.storage,
      expiryDate: form.value.expiryDate || null,
      note: form.value.note,
    };

    if (isEdit.value) {
      await updateFridgeItem(spaceId.value, itemId.value, payload);
    } else {
      await createFridgeItem(spaceId.value, payload);
    }

    uni.showToast({ title: isEdit.value ? '已保存' : '已加入', icon: 'success' });
    setTimeout(() => uni.navigateBack(), 600);
  } catch (error) {
    showError(error);
  } finally {
    pending.value = false;
  }
}

function confirmDelete(): void {
  if (pending.value) return;
  uni.showModal({
    title: '删除食材',
    content: `确定把「${form.value.name}」从冰箱里删掉吗？删除后无法恢复。`,
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (result) => {
      if (!result.confirm) return;
      pending.value = true;
      try {
        await deleteFridgeItem(spaceId.value, itemId.value);
        uni.showToast({ title: '已删除', icon: 'success' });
        setTimeout(() => uni.navigateBack(), 600);
      } catch (error) {
        showError(error);
      } finally {
        pending.value = false;
      }
    },
  });
}

onLoad((options) => {
  // uni-app 的 onLoad 参数类型是 any，这里手动取一下
  itemId.value = String((options as { id?: string })?.id ?? '');
  void load();
});
</script>

<style scoped>
.edit-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.tip { display: block; margin-top: 60rpx; color: var(--c-text-3); font-size: 24rpx; text-align: center; }

.form-card {
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}

.field-group { display: flex; flex-direction: column; gap: var(--s-2); margin-bottom: var(--s-4); }
.field-group:last-child { margin-bottom: 0; }
.field-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-2); }
.field-label { color: var(--c-text-2); font-size: 24rpx; }
.field-count { color: var(--c-text-3); font-size: 21rpx; }

.field-input {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 30rpx;
  font-weight: 500;
  box-sizing: border-box;
}
.field-textarea {
  width: 100%;
  min-height: 200rpx;
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 27rpx;
  line-height: 1.65;
  box-sizing: border-box;
}
.field-input.focused, .field-textarea.focused {
  border-color: var(--c-primary);
  background: var(--c-surface);
}
:deep(.field-placeholder) { color: var(--c-text-3); font-weight: 400; }

/* 数量 = 数字框 + 单位框，一行两段 */
.qty-row { display: flex; gap: var(--s-2); }
.qty-input { flex: 1; }
.qty-unit { flex: 0 0 40%; }

.chip-row { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.chip {
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 26rpx;
}
.chip.active {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}

.picker {
  height: var(--touch-min);
  display: flex;
  align-items: center;
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 28rpx;
  box-sizing: border-box;
}
.picker.placeholder { color: var(--c-text-3); }
.clear-date {
  align-self: flex-start;
  margin-top: var(--s-1);
  padding: var(--s-1) 0;
  color: var(--c-text-3);
  font-size: 22rpx;
}

.save-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 96rpx;
  margin-top: var(--s-4);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  font-weight: 500;
}
.save-btn.disabled { background: var(--c-disabled); }
.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 96rpx;
  margin-top: var(--s-3);
  border: 2rpx solid var(--c-danger-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-danger);
  font-size: 28rpx;
  font-weight: 500;
}
</style>
