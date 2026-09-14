<template>
  <view class="edit-page">
    <!--
      占位页：先把「我的」页 → 编辑资料的路径打通，界面还没实现。
      即使只是占位，也把当前资料显示出来——用户点进来至少能确认"现在是什么"，
      比一个空白页面加一句"开发中"有用。
    -->
    <view class="preview">
      <image class="avatar" :src="user?.avatarUrl || DEFAULT_AVATAR_URL" mode="aspectFill" />
      <text class="preview-name">{{ user ? user.nickname : '未登录' }}</text>
      <text v-if="user?.username" class="preview-account">@{{ user.username }}</text>
    </view>

    <view class="notice">
      <text class="notice-title">这个功能正在开发中</text>
      <text class="notice-body">
        上面是你现在的资料。等做好了，就能在这一页直接换头像、改昵称。
      </text>
    </view>

    <view class="plan">
      <text class="plan-title">接下来会加上</text>
      <view class="plan-item">
        <view class="plan-dot" />
        <text class="plan-text">换个头像：从相册选一张，或者直接拍</text>
      </view>
      <view class="plan-item">
        <view class="plan-dot" />
        <text class="plan-text">改个昵称：家人看到的就是这个名字</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
/**
 * 编辑资料页（**占位**）。
 *
 * 现在只做两件事：
 *   1. 把「我的」页 → 编辑资料 的跳转路径打通，方便联调；
 *   2. 把当前头像和昵称显示出来，让人知道点进来是在改什么。
 *
 * 真正要做的两件事还没实现：
 *   · 改昵称 —— 调 PATCH /users/me（后端接口已就绪，见 backend/app/api/v1/users.py）；
 *   · 换头像 —— 先 uni.chooseImage 选图，POST /uploads/image 拿到相对路径，再一起提交。
 *
 * 之所以先摆占位而不是直接做完整功能：这条路径（页面注册、跳转、取数）本身
 * 也可能出问题，先跑通再往里填内容，出问题时排查范围小得多。
 */

import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { DEFAULT_AVATAR_URL, fetchCurrentUser, type CurrentUser } from '../../services/user';
import { hasValidToken } from '../../utils/token';

const user = ref<CurrentUser | null>(null);

async function load(): Promise<void> {
  // 没登录就不发请求，免得白打一个必然 401 的接口。
  // 「我的」页在未登录时会把用户导向登录页，正常进不来这里。
  if (!hasValidToken()) return;

  try {
    user.value = await fetchCurrentUser();
  } catch (error) {
    // 拉不到（后端没启动、网络不通）就让上方显示成空态，不弹错误提示——
    // 这一页本来就是占位的，报错只会干扰联调
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

/* 当前资料预览：一眼看清"要改的是什么" */
.preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-5) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
/* 圆形头像：裁切交给容器，用户以后换成方图也能自动裁圆 */
.avatar {
  width: 160rpx;
  height: 160rpx;
  border-radius: 50%;
  background: var(--c-muted);
}
.preview-name { color: var(--c-text); font-size: 34rpx; font-weight: 500; }
.preview-account { color: var(--c-text-2); font-size: 24rpx; }

/* 开发中提示：走提醒色，和"出错了"（危险色）区分开 */
.notice {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-top: var(--s-3);
  padding: var(--s-3);
  border: 2rpx solid var(--c-warn-border);
  border-radius: var(--r-lg);
  background: var(--c-warn-bg);
}
.notice-title { color: var(--c-warn-text); font-size: 28rpx; font-weight: 500; }
.notice-body { color: var(--c-text-2); font-size: 24rpx; line-height: 1.6; }

.plan {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-4);
}
.plan-title { margin: 0 var(--s-1); color: var(--c-text-2); font-size: 23rpx; }
.plan-item { display: flex; align-items: flex-start; gap: var(--s-2); }
/* 用一个小圆点当项目符号，不用 emoji：emoji 依赖手机字体，各系统长得都不一样 */
.plan-dot {
  flex: 0 0 auto;
  width: 12rpx;
  height: 12rpx;
  margin-top: 14rpx;
  border-radius: 50%;
  background: var(--c-primary-weak);
}
.plan-text { flex: 1; color: var(--c-text); font-size: 26rpx; line-height: 1.6; }
</style>
