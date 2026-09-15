<template>
  <view class="profile-page">
    <!--
      用户信息卡片：一眼看清"现在是谁在登录"。
      整张卡片都可点：未登录 → 去登录页；已登录 → 去编辑资料页
      （编辑页可以换头像、改昵称）。
    -->
    <view class="user-card" hover-class="tap" @click="onUserCardTap">
      <image class="user-avatar" :src="displayAvatar" mode="aspectFill" />
      <view class="user-main">
        <text class="user-name">{{ user ? user.nickname : '未登录' }}</text>
        <text class="user-sub">{{ userSubText }}</text>
      </view>
      <text class="entry-arrow">›</text>
    </view>

    <!--
      菜单管理：只有创建人能改菜单（后端也会拦，这里隐藏只是体验），
      所以普通成员整块不显示，换成一句说明——否则他会点进去、填完表单才被拒绝，
      那是最难查的一种体验问题。
    -->
    <view v-if="isOwner" class="group">
      <text class="group-title">菜单管理</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goCategoryManage">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-clay)' }">
            <image class="entry-icon-img" src="/static/icons/tags.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">分类管理</text>
            <text class="entry-desc">增删改你们家的菜谱分类</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>

        <view class="entry-item" hover-class="tap" @click="goRecipeManage">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-sand)' }">
            <image class="entry-icon-img" src="/static/icons/form.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">菜品管理</text>
            <text class="entry-desc">添加、修改、删除菜谱</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <view v-else class="group">
      <view class="entry-group">
        <view class="entry-item">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-stone)' }">
            <image class="entry-icon-img" src="/static/icons/lock.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">菜谱由创建人维护</text>
            <text class="entry-desc">你可以随时翻阅；要改内容可以提醒一下创建人</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 其他家庭功能 -->
    <view class="group">
      <text class="group-title">其他</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goFavorites">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-clay)' }">
            <image class="entry-icon-img" src="/static/icons/star.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">我的收藏</text>
            <text class="entry-desc">你收藏的菜谱，只有自己能看到</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>

        <view class="entry-item" hover-class="tap" @click="goFridge">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-sage)' }">
            <image class="entry-icon-img" src="/static/icons/container.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">家庭冰箱</text>
            <text class="entry-desc">看看家里现在有什么菜</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>

        <view class="entry-item" hover-class="tap" @click="goOrders">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-sand)' }">
            <image class="entry-icon-img" src="/static/icons/rest.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">点单记录</text>
            <text class="entry-desc">客人点了什么、还有什么没做</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 设置：切换账号、切换家庭这类"配置类"动作统一收在这里，不散落在各页面 -->
    <view class="group">
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goSettings">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-stone)' }">
            <image class="entry-icon-img" src="/static/icons/setting.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">设置</text>
            <text class="entry-desc">切换账号、切换家庭</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
/**
 * 「我的」页。
 *
 * 几处设计值得说明：
 *
 * 1. 顶部是用户信息卡片（头像 + 昵称 + 用户名）。
 *    改造前这一页不显示"我是谁"，用户看不到自己登录的是哪个账号；
 *    家里几个人共用一台手机时，这个信息尤其重要。
 *    未登录时点它去登录页，已登录时点它去编辑资料页。
 *
 * 2. 加了「菜单管理」分组（分类管理 + 菜品管理）。
 *    菜单页现在是纯浏览，改菜谱统一收在这里。
 *    浏览和编辑分开，是为了避免翻菜谱时手滑进表单、甚至误删。
 *
 * 3. 摘掉了原本页面顶部那张「当前家庭 / 切换」卡片，改为一个「设置」入口。
 *    原因是切换家庭会影响菜谱、冰箱这些家庭共享数据——它属于"配置类"动作，
 *    不该和日常浏览混在同一个手势里。所有这类动作（切换账号、切换家庭）
 *    统一收进设置页，其余页面只负责显示、不提供切换。
 *
 * 4. 「菜单管理」只对**创建人**显示。
 *    创建人有三项专属权力：改菜单、解散家庭组、移除成员。
 *    普通成员看到的是"菜谱由创建人维护"的说明卡片——
 *    这比"让他点进去、填完表单才被拒绝"要好得多。
 *    隐藏只是体验，真正的拦截在后端（SpaceService.ensure_owner）。
 *
 * 5. 「其他」里新增「点单记录」入口，和家庭冰箱并列。
 *    家里来客人时，客人在菜单页选菜、提交点单，这一页是给做饭的人看的：
 *    谁点了什么、还有什么没做。
 *    它和冰箱有一处刻意不同——冰箱是长期共享的资料（只有创建人能改），
 *    点单是一次性的请求（任何成员都能提，提交者本人和创建人能管），
 *    所以这个入口对所有人显示。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { DEFAULT_AVATAR_URL, fetchCurrentUser, resolveAvatarUrl, type CurrentUser } from '../../services/user';
import { getCurrentSpace, resolveCurrentSpace } from '../../utils/space-context';
import { hasValidToken } from '../../utils/token';

/**
 * 当前登录的用户。
 * 为 null 有两种情况：确实没登录，或者登录态刚失效——
 * 两种都该显示成"未登录 + 去登录"，所以不需要再区分。
 */
const user = ref<CurrentUser | null>(null);

/** 卡片副标题：优先显示能确定身份的用户名 */
const userSubText = computed(() => {
  if (!user.value) return '点击登录或注册';
  // 改造前用微信登录的老账号还没有用户名，如实说明，别显示成一片空白
  return user.value.username ? `@${user.value.username}` : '还没有设置用户名';
});

/** 头像显示地址：本地占位图直接显示，服务端上传的相对路径拼完整地址 */
const displayAvatar = computed(() => resolveAvatarUrl(user.value?.avatarUrl));

/**
 * 拉取当前用户信息。
 *
 * 没登录时直接返回、不发请求——避免每次切到「我的」都白打一个必然 401 的接口。
 */
async function refreshUser(): Promise<void> {
  if (!hasValidToken()) {
    user.value = null;
    return;
  }
  try {
    user.value = await fetchCurrentUser();
  } catch (error) {
    // 拉不到（后端没启动、网络不通）时维持上一次的显示，
    // 而不是把卡片变成"未登录"——那会让人以为自己被登出了，白白慌一下
  }
}

/**
 * 点用户信息卡片。
 *
 * 两种状态各去一个地方：
 *   未登录 → 登录页（否则用户在这一页找不到任何"进账号"的入口）；
 *   已登录 → 编辑资料页（可换头像、改昵称）。
 */
function onUserCardTap(): void {
  uni.navigateTo({ url: user.value ? '/pages/profile/edit' : '/pages/auth/login' });
}

/**
 * 我是不是这个家的创建人。
 *
 * 只有创建人能改菜单，所以「菜单管理」入口按这个值显示/隐藏。
 * 注意这**只是体验**：后端每个写接口都会再校验一次，
 * 别人绕开界面直接调接口一样会被 403 拦住。
 */
const isOwner = ref(false);

async function refreshRole(): Promise<void> {
  // 先用本地缓存里的角色立刻定下来，页面不会闪一下再变
  isOwner.value = getCurrentSpace()?.myRole === 'admin';

  // 还没登录过就不主动请求，避免每次进「我的」都触发一次登录
  if (!hasValidToken()) return;

  try {
    await resolveCurrentSpace();
    isOwner.value = getCurrentSpace()?.myRole === 'admin';
  } catch (error) {
    // 拉取失败（例如后端没启动）时沿用缓存里的判断，不打断页面浏览
  }
}

/** 分类管理：增删改这个家的菜谱分类 */
function goCategoryManage() {
  uni.navigateTo({ url: '/pages/manage/category' });
}

/** 菜品管理：增删改菜谱 */
function goRecipeManage() {
  uni.navigateTo({ url: '/pages/manage/recipe' });
}

/** 我的收藏：个人私有域——同一家人各自收藏各自的，互相看不见 */
function goFavorites() {
  uni.navigateTo({ url: '/pages/favorites/index' });
}

/** 家庭冰箱：家庭共享功能，按当前家庭组展示 */
function goFridge() {
  uni.navigateTo({ url: '/pages/fridge/index' });
}

/**
 * 点单记录：家里来客人时点的单，以及还没做的。
 *
 * 这一页对所有人可见——点单本来就是给全家人看的"今天要做什么菜"；
 * 但"标记完成 / 删除"只有提交者本人和创建人能做，
 * 那个判断在后端算好了（canManage 字段），前端只管照着显示按钮。
 */
function goOrders() {
  uni.navigateTo({ url: '/pages/orders/index' });
}

/** 设置页：切换账号、切换家庭都在里面 */
function goSettings() {
  uni.navigateTo({ url: '/pages/settings/index' });
}

onShow(() => {
  refreshUser();
  refreshRole();
});
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

/* 用户信息卡片：整页视觉重心，所以用主色描边把它和下面的功能分组区分开 */
.user-card {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  min-height: 168rpx;
  padding: var(--s-3);
  border: 2rpx solid var(--c-primary-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
/* 圆形头像：裁切交给外层容器，这样用户以后换成方图也能自动裁成圆的 */
.user-avatar {
  flex: 0 0 auto;
  width: 112rpx;
  height: 112rpx;
  border-radius: 50%;
  background: var(--c-muted);
}
.user-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.user-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 34rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-sub {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 24rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 分组标题：把"设置类"和"功能类"分开，条目一多也不至于糊成一片 */
.group { margin-top: var(--s-4); }
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
/* 左侧一个小色块图标：比纯文字条目更容易扫读，也比塞一张图片轻 */
.entry-icon {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80rpx;
  height: 80rpx;
  border-radius: var(--r-sm);
  line-height: 1;
}
/* 图标用 SVG 而不是 emoji：emoji 依赖手机字体，同一台手机不同系统版本长得都不一样，
   也没法用设计令牌控制颜色；SVG 是矢量，随设计系统走，缩放不糊 */
.entry-icon-img { width: 44rpx; height: 44rpx; }
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
</style>
