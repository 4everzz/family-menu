<template>
  <view class="edit-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <view class="form-card">
        <view class="field-group">
          <text class="field-label">菜名</text>
          <input
            v-model="form.name"
            class="field-input"
            :class="{ focused: focusedField === 'name' }"
            placeholder="例如：番茄炒蛋"
            placeholder-class="field-placeholder"
            maxlength="64"
            @focus="focusedField = 'name'"
            @blur="focusedField = ''"
          />
        </view>

        <view class="field-group">
          <text class="field-label">归到哪一类（必选）</text>
          <!-- 分类清单完全来自后端，前端不硬编码。
               用户可以自己增删改分类，所以这里必须是动态的。 -->
          <view v-if="categories.length" class="category-picker">
            <view
              v-for="item in categories"
              :key="item.id"
              class="category-chip"
              :class="{ active: form.categoryId === item.id }"
              hover-class="tap"
              @click="form.categoryId = item.id"
            >
              {{ item.name }}
            </view>
          </view>
          <view v-else class="category-empty">
            这个家还没有分类。先去「我的 → 菜单管理 → 分类管理」建一个，才能添加菜谱。
          </view>
        </view>

        <view class="field-group">
          <view class="field-head">
            <text class="field-label">简介</text>
            <text class="field-count">{{ form.description.length }} / 2000</text>
          </view>
          <textarea
            v-model="form.description"
            class="field-textarea"
            :class="{ focused: focusedField === 'description' }"
            maxlength="2000"
            placeholder="一句话介绍这道菜，比如「油炸，外酥里嫩，约 20 分钟」"
            placeholder-class="field-placeholder"
            @focus="focusedField = 'description'"
            @blur="focusedField = ''"
          />
        </view>
        <!-- 菜品图片：可选。上传成功后存的是相对路径，显示时用 resolveFileUrl 拼完整地址 -->
        <view class="field-group">
          <text class="field-label">菜品图片（可选）</text>
          <view v-if="form.imageUrl" class="image-preview">
            <image class="image-preview-img" :src="resolveFileUrl(form.imageUrl)" mode="aspectFill" />
            <text class="image-remove" hover-class="tap" @click="removeImage">移除图片</text>
          </view>
          <view v-else class="image-pick" hover-class="tap" @click="pickImage">
            <text class="image-pick-sign">＋</text>
            <text class="image-pick-hint">{{ uploading ? '正在上传…' : '从相册选一张' }}</text>
          </view>
        </view>

        <!--
          辣度设置（对照旧小程序版的「菜品设置」页）。
          「支持哪几档」和「默认哪一档」是两个问题，所以分两步选：
          前者是这道菜**能不能**做微辣/特辣，后者是**不特别说明时**按哪一档记。
        -->
        <view class="field-group">
          <text class="field-label">辣度设置（可多选）</text>
          <view class="spice-grid">
            <view
              v-for="level in SPICE_LEVELS"
              :key="level"
              class="spice-chip"
              :class="{ active: form.spiceOptions.includes(level) }"
              hover-class="tap"
              @click="toggleSpice(level)"
            >{{ level }}</view>
          </view>
          <text class="field-tip">一档都不选，表示点这道菜时不问辣度（汤、饮品通常这样）。</text>

          <!-- 默认辣度只从"已选中的档位"里挑，所以它必须出现在上面之后 -->
          <template v-if="form.spiceOptions.length">
            <text class="field-label">默认辣度</text>
            <view class="spice-grid">
              <view
                v-for="level in form.spiceOptions"
                :key="level"
                class="spice-chip"
                :class="{ active: form.defaultSpice === level }"
                hover-class="tap"
                @click="form.defaultSpice = level"
              >{{ level }}</view>
            </view>
            <text class="field-tip">点单时客人没特别说，就按这一档记。</text>
          </template>
        </view>

        <!-- 「今天不做」：临时开关，不是库存 -->
        <view class="field-group">
          <view class="switch-row" hover-class="tap" @click="form.isSoldOut = !form.isSoldOut">
            <text class="field-label">今天不做</text>
            <view class="switch-track" :class="{ on: form.isSoldOut }">
              <view class="switch-knob" />
            </view>
          </view>
          <text class="field-tip">
            打开后这道菜仍留在菜单里，但暂时不能加进点单——比如今天食材没了。随时可以关掉。
          </text>
        </view>
      </view>

      <view class="save-btn" :class="{ disabled: !canSave }" hover-class="tap" @click="submit">
        {{ pending ? '正在保存…' : isEdit ? '保存修改' : '加进菜谱' }}
      </view>

      <!-- 删除放在这个页面里，列表页的卡片上不放开删的入口，少一次误触 -->
      <view v-if="isEdit" class="delete-btn" hover-class="tap" @click="confirmDelete">删除这道菜</view>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 菜谱编辑页：新增和编辑共用一个页面。
 *
 * 为什么合一？
 *   两种模式的字段完全一样、校验完全一样，唯一的差别是"加载已有数据"和
 *   "调新增还是调修改"。拆成两个页面会带来两份几乎相同的表单代码，
 *   以后加一个字段要改两处，早晚会漏。
 *
 * 用法（入口都在「我的 → 菜单管理 → 菜品管理」）：
 *   /pages/recipe/edit        → 新增
 *   /pages/recipe/edit?id=12  → 编辑第 12 道菜
 *
 * 注意本页不再从菜单页进入——菜单页已经改成纯浏览，
 * 点菜谱卡片进的是只读详情页 pages/recipe/detail.vue。
 */

import { computed, reactive, ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { fetchCategories } from '../../services/category';
import { resolveFileUrl } from '../../services/http';
import { uploadImage, chooseImageFromAlbum } from '../../services/upload';
import { SPICE_LEVELS, createRecipe, deleteRecipe, fetchRecipe, updateRecipe } from '../../services/recipe';
import type { SpiceLevel } from '../../services/recipe';
import { getCurrentSpaceId } from '../../utils/space-context';
import { showError } from '../../utils/format';
import { DANGER } from '../../utils/theme';

const spaceId = ref('');
const recipeId = ref('');
const categories = ref<Category[]>([]);
const loading = ref(true);
/** 读取失败时的提示。为空才正常渲染表单——否则编辑一道读不出来的菜会显示成空白新增表单 */
const errorMessage = ref('');
/** 请求进行中标记：防止连点导致重复提交（新增接口不是幂等的，连点会加出两条） */
const pending = ref(false);
/** 当前聚焦的字段名，用来把输入框描边点亮。小程序没有 CSS :focus，只能用 JS 标记 */
const focusedField = ref('');

/** 表单内容。用 reactive 而不是一堆 ref，改起来更整齐 */
const form = reactive({
  name: '',
  categoryId: '',
  description: '',
  imageUrl: '',
  /**
   * 这道菜支持哪几档辣度（多选）。
   * 空数组 = 点这道菜时不问辣度，汤和饮品通常就是这样。
   */
  spiceOptions: [] as SpiceLevel[],
  /** 默认辣度。必须落在 spiceOptions 里；没得选时为空串 */
  defaultSpice: '' as SpiceLevel | '',
  /** 「今天不做」 */
  isSoldOut: false,
});
/** 图片正在上传中：此时禁用再选，避免同一张图传两次 */
const uploading = ref(false);

/**
 * 勾选 / 取消一个辣度档位。
 *
 * 每次改完都**按 SPICE_LEVELS 的顺序重排**，而不是保持用户勾选的先后：
 * 点单时那几个按钮的顺序应该人人一样（不辣 → 微辣 → 正常辣 → 特辣），
 * 否则同一道菜在两个人的手机上排出来不一样。
 */
function toggleSpice(level: SpiceLevel): void {
  const index = form.spiceOptions.indexOf(level);
  if (index >= 0) form.spiceOptions.splice(index, 1);
  else form.spiceOptions.push(level);

  form.spiceOptions = SPICE_LEVELS.filter((item) => form.spiceOptions.includes(item));

  // 默认辣度必须落在选中的档位里：原来选的那档被取消了，就退回第一档；
  // 一档都不剩时清空——"不问辣度却记着默认值"是自相矛盾的数据
  if (!form.spiceOptions.length) {
    form.defaultSpice = '';
  } else if (!form.spiceOptions.includes(form.defaultSpice as SpiceLevel)) {
    form.defaultSpice = form.spiceOptions[0];
  }
}

const isEdit = computed(() => !!recipeId.value);
/** 菜名必填、分类必选（后端也校验，这里只是避免白跑一次请求） */
const canSave = computed(() => !pending.value && !!form.name.trim() && !!form.categoryId);

async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    await ensureLogin();
    spaceId.value = getCurrentSpaceId();

    // 正常流程不会走到这里（入口页已经拦了），防御一下：没有家庭组就没法存菜谱
    if (!spaceId.value) {
      showError('还没有选择家庭组');
      setTimeout(() => uni.navigateBack(), 900);
      return;
    }

    categories.value = await fetchCategories(spaceId.value);

    if (isEdit.value) {
      const recipe = await fetchRecipe(spaceId.value, recipeId.value);
      form.name = recipe.name;
      form.categoryId = recipe.categoryId;
      form.description = recipe.description;
      form.imageUrl = recipe.imageUrl;
      // 复制一份数组而不是直接引用：直接引用的话，用户取消勾选会把
      // 从接口拿到的那个对象也改掉，虽然这里看不出问题，但那种"改着改着把源数据改了"的坑很难查
      form.spiceOptions = [...recipe.spiceOptions];
      form.defaultSpice = recipe.defaultSpice;
      form.isSoldOut = recipe.isSoldOut;
      uni.setNavigationBarTitle({ title: '编辑菜谱' });
    } else {
      // 不预选分类（用户拍板）：让用户自己点，而不是替他做主塞进「热菜」。
      // 每道菜必须属于一个分类（数据库约束），所以保存按钮在选好之前是置灰的。
      form.categoryId = '';
      uni.setNavigationBarTitle({ title: '新增菜谱' });
    }
  } catch (error) {
    // 编辑一道读不出来的菜时，不能落回一张空白表单——那会让人以为数据丢了。
    // 用页面内的错误卡 + 重试代替 toast，用户能原地重试。
    errorMessage.value = error instanceof Error ? error.message : '读取失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/**
 * 选图并上传。选完立刻传（而不是等保存时一起传），原因有二：
 *   1. 上传失败能当场告诉用户，不用等到"点保存"才发现图传不上去；
 *   2. 保存接口只收 image_url 字符串，把"传文件"和"存表单"两件事彻底分开。
 */
function pickImage(): void {
  if (uploading.value) return;
  chooseImageFromAlbum()
    .then(async (filePath) => {
      uploading.value = true;
      try {
        const data = await uploadImage(filePath);
        form.imageUrl = data.url;
        uni.showToast({ title: '图片已上传', icon: 'none' });
      } catch (error) {
        showError(error);
      } finally {
        uploading.value = false;
      }
    })
    .catch((error) => {
      // 用户在选图界面点取消也会走到这里，不打扰
      const message = error instanceof Error ? error.message : '';
      if (message.includes('cancel')) return;
      showError(error);
    });
}

/** 移除已选图片：只清掉表单里的地址，保存后才真正不再关联 */
function removeImage(): void {
  form.imageUrl = '';
}

async function submit(): Promise<void> {
  if (!canSave.value) return;
  pending.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      categoryId: form.categoryId,
      description: form.description,
      imageUrl: form.imageUrl,
      spiceOptions: form.spiceOptions,
      // 没选默认档就交给后端取第一档（传空串会被后端当成"没指定"）
      defaultSpice: form.defaultSpice || form.spiceOptions[0] || '',
      isSoldOut: form.isSoldOut,
    };

    if (isEdit.value) await updateRecipe(spaceId.value, recipeId.value, payload);
    else await createRecipe(spaceId.value, payload);

    uni.showToast({ title: isEdit.value ? '已保存' : '已添加', icon: 'success' });
    // 等一下再返回，让提示能被看见；列表页的 onShow 会自动刷新出最新数据
    setTimeout(() => uni.navigateBack(), 600);
  } catch (error) {
    showError(error instanceof Error ? error.message : '保存失败，请重试');
  } finally {
    pending.value = false;
  }
}

/**
 * 删除菜谱。
 *
 * 必须二次确认：本版本「谁都能删」是由权限模型决定的（见后端 RecipeService 的说明），
 * 代价就用这道确认来兜——菜谱是全家一起攒的，误删一条别人加的菜很伤感情。
 */
function confirmDelete(): void {
  if (pending.value) return;
  uni.showModal({
    title: '删除这道菜',
    content: `确定要把「${form.name}」从家庭菜谱里删掉吗？删除后无法恢复。`,
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (result) => {
      if (!result.confirm) return;
      pending.value = true;
      try {
        await deleteRecipe(spaceId.value, recipeId.value);
        uni.showToast({ title: '已删除', icon: 'success' });
        setTimeout(() => uni.navigateBack(), 600);
      } catch (error) {
        showError(error instanceof Error ? error.message : '删除失败，请重试');
      } finally {
        pending.value = false;
      }
    },
  });
}

onLoad((options) => {
  recipeId.value = String(options?.id ?? '');
  void load();
});
</script>

<style scoped>
.edit-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.tip { display: block; margin-top: var(--s-6); color: var(--c-text-3); font-size: 24rpx; text-align: center; }

.error-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-4);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-danger-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.error-text { color: var(--c-danger); font-size: 27rpx; font-weight: 500; }
.retry-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--touch-min);
  margin-top: var(--s-2);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: #fff;
  font-size: 26rpx;
}

/* 整张表单放一张卡片里：输入框之间靠间距分组，视觉上比"一堆散落的框"整齐得多 */
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
  min-height: 320rpx;
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 27rpx;
  line-height: 1.65;
  box-sizing: border-box;
}
/* 聚焦态：小程序没有 CSS :focus，靠 JS 加类名。
   不加这个的话，用户点进输入框没有任何反馈，会不确定"到底选中了没"。 */
.field-input.focused, .field-textarea.focused {
  border-color: var(--c-primary);
  background: var(--c-surface);
}
:deep(.field-placeholder) { color: var(--c-text-3); font-weight: 400; }

.category-picker { display: flex; flex-wrap: wrap; gap: var(--s-2); }
/* 药丸形标签：够大（88rpx 高）能稳定点中，又比一排大按钮省地方 */
.category-chip {
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
.category-chip.active {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}
.category-empty {
  padding: var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-md);
  color: var(--c-text-2);
  font-size: 24rpx;
  line-height: 1.6;
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
.page-note { display: block; margin-top: var(--s-4); color: var(--c-text-3); font-size: 22rpx; text-align: center; }

/* 图片选择区：虚线框表达"可以放东西进来"，比一个光秃秃的按钮直观 */
.image-pick {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-1);
  min-height: 200rpx;
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.image-pick-sign { color: var(--c-text-3); font-size: 52rpx; line-height: 1; }
.image-pick-hint { color: var(--c-text-2); font-size: 23rpx; }

.image-preview { display: flex; align-items: flex-end; gap: var(--s-3); }
.image-preview-img { width: 200rpx; height: 200rpx; border-radius: var(--r-md); border: 2rpx solid var(--c-border); background: var(--c-muted); }
.image-remove { padding: 30rpx var(--s-2); margin: -30rpx calc(-1 * var(--s-2)); color: var(--c-danger); font-size: 23rpx; }

/* 字段下面那行小字说明 */
.field-tip { color: var(--c-text-3); font-size: 22rpx; line-height: 1.6; }

/* 辣度档位：两列，各占 88rpx 高，和别处的选项一样好点 */
.spice-grid { display: flex; flex-wrap: wrap; gap: var(--s-2); }
.spice-chip {
  flex: 0 0 calc(50% - var(--s-1));
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 26rpx;
  box-sizing: border-box;
}
.spice-chip.active {
  border-color: var(--c-primary);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-weight: 500;
}

/* 「今天不做」的开关：轨道 + 圆点自己画，不为了一个开关引组件库。
   整行都可点（不只那个小开关），手指不用瞄准 */
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  min-height: var(--touch-min);
}
.switch-track {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  width: 96rpx;
  height: 56rpx;
  padding: 4rpx;
  border-radius: var(--r-pill);
  background: var(--c-border-strong);
  box-sizing: border-box;
}
.switch-track.on { background: var(--c-primary); }
.switch-knob {
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2rpx 6rpx rgba(28, 25, 23, 0.18);
  transition: transform 0.16s ease;
}
.switch-track.on .switch-knob { transform: translateX(40rpx); }
</style>
