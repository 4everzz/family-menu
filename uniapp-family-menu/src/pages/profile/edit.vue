<template>
  <view class="edit-page">
    <!-- 头像：整块可点，点开选图或拍照，上传后存相对路径 -->
    <view class="group">
      <text class="group-title">头像</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="onAvatarTap">
          <view class="entry-main">
            <text class="entry-name">我的头像</text>
            <text class="entry-desc">{{ hasCustomAvatar ? '点一下换一张' : '点一下从相册选或拍照' }}</text>
          </view>
          <image class="avatar" :src="displayAvatar" mode="aspectFill" />
          <text class="entry-arrow">›</text>
        </view>
        <view v-if="hasCustomAvatar" class="entry-item reset-item" hover-class="tap" @click="onResetAvatar">
          <view class="entry-main">
            <text class="entry-name danger-text">恢复默认头像</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 昵称：改完点保存，调 POST /users/me 只传 nickname -->
    <view class="group">
      <text class="group-title">昵称</text>
      <view class="entry-group">
        <view class="nickname-row">
          <input
            class="nickname-input"
            v-model="nicknameInput"
            type="text"
            :maxlength="20"
            placeholder="给家人们留个名字"
            placeholder-class="nickname-placeholder"
          />
        </view>
      </view>
      <text class="counter">{{ trimmedNickname.length }}/20</text>
    </view>

    <button
      class="save-btn"
      hover-class="tap"
      :class="{ 'save-btn--disabled': !canSave }"
      :disabled="!canSave"
      @click="onSaveNickname"
    >
      {{ saving ? '保存中…' : '保存昵称' }}
    </button>
  </view>
</template>

<script setup lang="ts">
/**
 * 编辑资料页（真实功能）。
 *
 * 能做两件事，都走后端已就绪的接口：
 *   · 改昵称 —— updateCurrentUser({ nickname })，后端 POST /users/me（PATCH 的兼容入口）；
 *   · 换头像 —— 先 uni.chooseImage 选图，uploadImage 拿到相对路径 /uploads/...，
 *     再 updateCurrentUser({ avatarUrl }) 一起落库；撤销自定义头像则传 null 回到默认占位图。
 *
 * 头像相对路径必须过 resolveAvatarUrl 才能显示：本地 /static 占位图直接用，
 * 服务端 /uploads 路径才拼完整地址——否则 App / H5 里会裂图。
 *
 * 改完之后「我的」页和设置页都会在 onShow 重新拉取，所以这里改完本地即时刷新即可，
 * 不用发全局事件。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import {
  DEFAULT_AVATAR_URL,
  fetchCurrentUser,
  resolveAvatarUrl,
  updateCurrentUser,
  type CurrentUser,
} from '../../services/user';
import { chooseImageFromAlbum, uploadImage } from '../../services/upload';
import { hasValidToken } from '../../utils/token';

const user = ref<CurrentUser | null>(null);

/** 昵称输入框的本地副本：改之前先 Edit，保存时才提交，避免一打字就打接口 */
const nicknameInput = ref('');

/** 防连点：头像上传/昵称保存都用一个统一的忙标记即可，两者不会同时进行 */
const busy = ref(false);
/** 昵称保存专属的忙标记：按钮文案要显示"保存中"，和头像的忙标记分开更直观 */
const saving = ref(false);

/** 当前头像显示地址：统一走 resolveAvatarUrl，本地/服务端两套来源都正确 */
const displayAvatar = computed(() => resolveAvatarUrl(user.value?.avatarUrl));

/** 有没有自定义头像（区别于默认占位图），决定要不要显示"恢复默认" */
const hasCustomAvatar = computed(() => {
  const url = user.value?.avatarUrl;
  return !!url && url !== DEFAULT_AVATAR_URL;
});

/** 去掉首尾空白后的昵称：计数、校验都用它，避免"全空格"绕过后端 */
const trimmedNickname = computed(() => nicknameInput.value.trim());

/** 昵称到底改了没：没动就不让保存，省一次无意义的请求 */
const nicknameDirty = computed(() => {
  if (!user.value) return false;
  return trimmedNickname.value.length > 0 && trimmedNickname.value !== user.value.nickname;
});

/** 保存按钮是否可点：没在保存中、且昵称确实变了 */
const canSave = computed(() => !saving.value && nicknameDirty.value);

/**
 * 拉取当前用户，并初始化昵称输入框。
 * 没登录就不发请求——「我的」页未登录会导向登录页，正常进不来这里。
 */
async function load(): Promise<void> {
  if (!hasValidToken()) return;
  try {
    const u = await fetchCurrentUser();
    user.value = u;
    nicknameInput.value = u.nickname;
  } catch (error) {
    // 拉不到（后端没启动、网络不通）就让上方显示成空态，不弹错误——
    // 这一页本来就要靠数据才能用，报错只会干扰
  }
}

/**
 * 点头像：选图 → 上传 → 保存。
 * 取消选图（uni.chooseImage 的 fail cancel）按"用户主动放弃"处理，不弹错误。
 */
async function onAvatarTap(): Promise<void> {
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
    user.value = await updateCurrentUser({ avatarUrl: result.url });
    uni.showToast({ title: '头像已更新', icon: 'success' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '上传失败', icon: 'none' });
  } finally {
    busy.value = false;
  }
}

/** 恢复默认头像：传 null，后端把 avatar_url 置空，前端回退到占位图 */
async function onResetAvatar(): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  try {
    user.value = await updateCurrentUser({ avatarUrl: null });
    uni.showToast({ title: '已恢复默认头像', icon: 'success' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '操作失败', icon: 'none' });
  } finally {
    busy.value = false;
  }
}

/** 保存昵称：前端先校验非空（后端是权威，但空值没必要打一次请求） */
async function onSaveNickname(): Promise<void> {
  if (!canSave.value) return;

  const next = trimmedNickname.value;
  if (!next) {
    uni.showToast({ title: '昵称不能为空', icon: 'none' });
    return;
  }

  saving.value = true;
  try {
    const updated = await updateCurrentUser({ nickname: next });
    user.value = updated;
    nicknameInput.value = updated.nickname;
    uni.showToast({ title: '昵称已保存', icon: 'success' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '保存失败', icon: 'none' });
  } finally {
    saving.value = false;
  }
}

onShow(load);
</script>

<style scoped>
.edit-page {
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
/* 恢复默认那一行：整条可点，文案用危险色，和"换头像"区分开 */
.reset-item { min-height: 112rpx; }
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

/* 圆形头像：裁切交给容器，换成方图也能自动裁圆 */
.avatar {
  flex: 0 0 auto;
  width: 88rpx;
  height: 88rpx;
  border-radius: 50%;
  background: var(--c-muted);
}

.nickname-row {
  display: flex;
  align-items: center;
  min-height: 120rpx;
  padding: var(--s-2) var(--s-3);
}
.nickname-input {
  flex: 1;
  color: var(--c-text);
  font-size: 29rpx;
}
.nickname-placeholder { color: var(--c-text-3); }
/* 计数：靠右小字，提醒别超 64 */
.counter {
  display: block;
  margin: var(--s-1) var(--s-1) 0;
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: right;
}

/* 保存按钮：用主色，和浏览类条目拉开层级 */
.save-btn {
  margin: var(--s-5) var(--s-1) 0;
  border: none;
  border-radius: var(--r-lg);
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  line-height: 88rpx;
}
.save-btn--disabled { background: var(--c-disabled); color: #fff; }
/* uni-app 的 button 默认带一条 ::after 边框，这里清掉，免得和圆角描边叠出双线 */
.save-btn::after { border: none; }

/* 破坏性操作：文案用危险色，提示这条和上面的浏览类条目不是一回事 */
.danger-text { color: var(--c-danger); }
</style>
