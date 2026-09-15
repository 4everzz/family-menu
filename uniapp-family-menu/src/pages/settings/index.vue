<template>
  <view class="settings-page">
    <!-- 账号：先让用户看清"现在是谁在登录"，再决定要不要换 -->
    <view class="group">
      <text class="group-title">账号</text>
      <view class="entry-group">
        <view class="identity">
          <image class="avatar-img" :src="avatarUrl || DEFAULT_AVATAR_URL" mode="aspectFill" />
          <view class="identity-main">
            <text class="identity-name">{{ nickname || '未登录' }}</text>
            <text class="identity-desc">{{ identityDesc }}</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 家庭：切换、创建、加入统一收在这里，菜单页不再有入口 -->
    <view class="group">
      <text class="group-title">家庭</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goSpace">
          <view class="entry-main">
            <text class="entry-name">切换家庭</text>
            <text class="entry-desc">当前：{{ spaceName || '未加入家庭组' }}</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 账号操作：破坏性操作用危险色，和上面的浏览类条目区分开 -->
    <view class="group">
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="switchAccount">
          <view class="entry-main">
            <text class="entry-name danger-text">退出登录</text>
            <text class="entry-desc">清除本机登录状态，回到登录页</text>
          </view>
        </view>
      </view>
    </view>

    <text class="page-note">更多设置项会在后续模块加入</text>
  </view>
</template>

<script setup lang="ts">
/**
 * 设置页。
 *
 * 为什么要有这一页？
 *   「切换家庭」原来分散在菜单页和「我的」页的卡片上，点一下就能换家。
 *   但换家会连带影响菜谱、冰箱这些家庭共享数据——它属于"配置类"动作，
 *   不该和"看菜单"混在同一个手势里。所以统一收进设置页，
 *   菜单页只负责显示"现在看的是哪个家"，不再提供切换。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { DEFAULT_AVATAR_URL, fetchCurrentUser, resolveAvatarUrl } from '../../services/user';
import { LOGIN_PATH } from '../../services/auth-api';
import { clearToken, hasValidToken } from '../../utils/token';
import { DANGER } from '../../utils/theme';
import { getCurrentSpaceName, resolveCurrentSpace, setCurrentSpace } from '../../utils/space-context';

const nickname = ref('');
const username = ref('');
const avatarUrl = ref('');
const spaceName = ref('');
/** 防止连点导致重复弹窗/重复请求 */
const pending = ref(false);

/** 身份卡片的副标题：把"有没有登录、用的是哪个用户名"说清楚 */
const identityDesc = computed(() => {
  if (!hasValidToken()) return '还没有登录';
  // 改造前用微信登录的老账号还没有用户名，如实说明，别留一片空白
  return username.value ? `@${username.value}` : '微信登录的账号，还没有用户名';
});

async function refresh(): Promise<void> {
  // 先用本地缓存把界面填上，避免进页面先空一下
  spaceName.value = getCurrentSpaceName();

  if (!hasValidToken()) return;

  try {
    const user = await fetchCurrentUser();
    nickname.value = user.nickname;
    username.value = user.username;
    avatarUrl.value = resolveAvatarUrl(user.avatarUrl);
  } catch (error) {
    // 读取失败（例如后端没启动）不打断页面，保留默认文案
  }

  try {
    await resolveCurrentSpace();
    spaceName.value = getCurrentSpaceName();
  } catch (error) {
    // 同上：拿不到列表就沿用缓存里的名字
  }
}

/** 切换/创建/加入家庭组都在家庭组页面里 */
function goSpace(): void {
  uni.navigateTo({ url: '/pages/space/index' });
}

/**
 * 退出登录。
 *
 * 令牌是"这台设备上的登录凭证"，清掉它 = 这台设备上不再有人登录。
 * 两样东西必须一起清：
 *   · 令牌本身；
 *   · 家庭组缓存——否则下一个人登录后还带着上一个人的"当前家庭"，
 *     界面上会先闪出别人的家庭名，看着像串号（数据本身取不到，因为后端按令牌校验，
 *     但显示出来会让人以为泄露了）。
 *
 * 退出后用 reLaunch 而不是 navigateTo：语义上这是"换一个会话重新开始"，
 * 让页面栈整个清空比往上面再压一页更干净——否则用户按返回还能退回刚退出的界面。
 */
function switchAccount(): void {
  if (pending.value) return;
  uni.showModal({
    title: '退出登录',
    content: '会清除本机保存的登录状态（含当前家庭组），之后需要重新输入用户名和密码。',
    confirmText: '退出',
    confirmColor: DANGER,
    success: (res) => {
      if (!res.confirm) return;
      pending.value = true;

      clearToken();
      setCurrentSpace(null);
      spaceName.value = '';
      nickname.value = '';
      username.value = '';
      avatarUrl.value = '';

      pending.value = false;
      uni.reLaunch({ url: LOGIN_PATH });
    },
  });
}

onShow(refresh);
</script>

<style scoped>
.settings-page {
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

/* 身份卡片：比普通条目高一点，让"我是谁"这个信息更醒目 */
.identity {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  min-height: 136rpx;
  padding: var(--s-2) var(--s-3);
}
/* 头像是圆形：裁切交给容器，用户以后换成方图也能自动裁圆。
   没设头像时后端给的是空值，前端统一兜到默认占位图（见 services/user.ts），
   所以这里不需要"没有图就显示文字"的分支。 */
.avatar-img {
  flex: 0 0 auto;
  width: 88rpx;
  height: 88rpx;
  border-radius: 50%;
  background: var(--c-muted);
}
.identity-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.identity-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 30rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.identity-desc { color: var(--c-text-2); font-size: 23rpx; }

.entry-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 120rpx;
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

/* 破坏性操作：文案用危险色，提示这条和上面的浏览类条目不是一回事 */
.danger-text { color: var(--c-danger); }

.page-note {
  display: block;
  margin-top: var(--s-5);
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: center;
}
</style>
