<template>
  <view class="space-page">
    <!-- 当前家庭组：切换后冰箱等家庭共享数据都会跟着变 -->
    <view class="current-card">
      <text class="current-label">当前家庭</text>
      <text class="current-name">{{ currentName || '未加入家庭组' }}</text>
    </view>

    <view v-if="loading" class="tip">正在读取家庭组…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <text class="error-hint">
        家庭组功能需要后端处于启动状态；在微信开发者工具里还需勾选「不校验合法域名」。
      </text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <!--
        分成「我创建的」和「我加入的」两组，各自带额度用量（如 1 / 2）。
        分组的依据是 my_role：admin = 我创建的，member = 我加入的。
        用 sections 数组渲染、卡片只写一遍——两个分组结构完全一样，
        复制两份的话以后改卡片就要改两处，早晚漏一处。
      -->
      <view v-for="section in sections" :key="section.key" class="section">
        <view class="section-head">
          <text class="group-title">{{ section.title }}</text>
          <text class="group-quota" :class="{ danger: section.full }">{{ section.quotaText }}</text>
        </view>

        <text v-if="!section.items.length" class="section-empty">{{ section.emptyText }}</text>

        <view
          v-for="item in section.items"
          :key="item.id"
          class="space-item"
          :class="{ selected: item.id === currentId }"
          hover-class="tap"
          @click="switchTo(item)"
        >
          <view class="space-row">
            <view class="space-main">
              <text class="space-name">{{ item.name }}</text>
              <text class="space-meta">{{ roleText(item) }}</text>
            </view>
            <text v-if="item.id === currentId" class="badge">当前</text>
          </view>

          <!-- 邀请码只有创建人看得到，这是后端控制的，普通成员这里不会有这一行 -->
          <view v-if="item.inviteCode" class="invite-row" hover-class="tap" @click.stop="copyCode(item.inviteCode)">
            <text class="invite-label">邀请码</text>
            <text class="invite-code">{{ item.inviteCode }}</text>
            <text class="invite-action">复制</text>
          </view>

          <!--
            管理操作：创建人多了「成员管理」和「解散」，普通成员只有「退出」。
            这里按角色隐藏只是体验，真正的防线在后端——创建人调退出接口会被 400 拦住。
          -->
          <view class="manage-row">
            <text
              v-if="item.myRole === 'admin'"
              class="manage-link"
              hover-class="tap"
              @click.stop="toggleMembers(item)"
            >{{ managingId === item.id ? '收起成员' : '成员管理' }}</text>
            <text v-else class="manage-link" hover-class="tap" @click.stop="confirmLeave(item)">退出家庭组</text>
            <text v-if="item.myRole === 'admin'" class="manage-link danger" hover-class="tap" @click.stop="confirmDissolve(item)">解散</text>
          </view>

          <!-- 成员面板：只在展开时渲染，避免每个家庭组都去拉一次成员接口 -->
          <view v-if="managingId === item.id" class="member-panel" @click.stop>
            <text v-if="membersLoading" class="member-tip">正在读取成员…</text>
            <template v-else>
              <text v-if="!members.length" class="member-tip">暂时没有读到成员</text>
              <view v-for="m in members" :key="m.userId" class="member-row">
                <view class="member-main">
                  <text class="member-name">{{ m.nickname || '微信用户' }}</text>
                  <text class="member-role">{{ m.isOwner ? '创建人' : '成员' }}</text>
                </view>
              <text
                v-if="!m.isOwner"
                class="member-remove"
                hover-class="tap"
                @click.stop="confirmRemove(item, m)"
              >移除</text>
              </view>
            </template>
          </view>
        </view>
      </view>

      <view v-if="!spaces.length" class="empty-card">
        <text class="empty-title">还没有家庭组</text>
        <text class="empty-copy">创建一个，把家人拉进来；也可以让家人把邀请码发给你，用下面的入口加入。</text>
      </view>

      <view class="action-card">
        <view class="action-head" hover-class="tap" @click="creating = !creating">
          <text class="action-name">创建家庭组</text>
          <view class="action-tail">
            <text v-if="hasQuota" class="action-quota" :class="{ danger: createFull }">
              {{ quota.owned }} / {{ quota.maxOwned }}
            </text>
            <text class="action-sign">{{ creating ? '收起' : '展开' }}</text>
          </view>
        </view>
        <view v-if="creating" class="action-body">
          <!-- 额度已满时先把话说清楚，而不是让用户填完名字才被拒绝 -->
          <text v-if="createFull" class="limit-hint">
            您创建的家庭组数量已达上限（{{ quota.maxOwned }} 个）。解散一个之后可以再创建。
          </text>
          <input
            v-model="createName"
            class="field"
            :disabled="createFull"
            placeholder="给家庭组起个名字，例如「张家」"
            placeholder-class="field-placeholder"
            maxlength="32"
          />
          <view class="submit-btn" :class="{ disabled: createDisabled }" hover-class="tap" @click="submitCreate">创建</view>
        </view>
      </view>

      <view class="action-card">
        <view class="action-head" hover-class="tap" @click="joining = !joining">
          <text class="action-name">用邀请码加入</text>
          <view class="action-tail">
            <text v-if="hasQuota" class="action-quota" :class="{ danger: joinFull }">
              {{ quota.joined }} / {{ quota.maxJoined }}
            </text>
            <text class="action-sign">{{ joining ? '收起' : '展开' }}</text>
          </view>
        </view>
        <view v-if="joining" class="action-body">
          <text v-if="joinFull" class="limit-hint">
            您加入的家庭组数量已达上限（{{ quota.maxJoined }} 个）。退出一个之后可以再加入。
          </text>
          <input
            v-model="joinCode"
            class="field"
            :disabled="joinFull"
            placeholder="输入家人分享的 8 位邀请码"
            placeholder-class="field-placeholder"
            maxlength="16"
          />
          <view class="submit-btn" :class="{ disabled: joinDisabled }" hover-class="tap" @click="submitJoin">加入</view>
        </view>
      </view>

      <text class="page-note">创建家庭组的人即「创建人」：能看到邀请码、能修改菜单、也能解散这个家；其他成员可以随时翻阅菜谱。</text>
      <text v-if="hasQuota" class="page-note">
        一个人最多创建 {{ quota.maxOwned }} 个、最多加入 {{ quota.maxJoined }} 个家庭组。
      </text>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import {
  getCurrentSpaceId,
  getCurrentSpaceName,
  resolveCurrentSpace,
  setCurrentSpace,
} from '../../utils/space-context';
import type { SpaceInfo } from '../../utils/space-context';
import {
  createSpace,
  dissolveSpace,
  fetchSpaceMembers,
  fetchSpaceQuota,
  joinSpace,
  leaveSpace,
  removeSpaceMember,
} from '../../services/space';
import type { SpaceMember, SpaceQuota } from '../../services/space';
import { ensureLogin } from '../../services/auth-api';
import { DANGER, PRIMARY } from '../../utils/theme';

const spaces = ref<SpaceInfo[]>([]);
const currentId = ref(getCurrentSpaceId());
const currentName = ref(getCurrentSpaceName());
const loading = ref(true);
const errorMessage = ref('');

const creating = ref(false);
const createName = ref('');
const joining = ref(false);
const joinCode = ref('');
/** 请求进行中标记：防止连点导致重复创建 */
const pending = ref(false);

/** 当前展开成员管理的家庭组 id；同一时间只展开一个，否则列表会长得没法看 */
const managingId = ref<string | null>(null);
const members = ref<SpaceMember[]>([]);
const membersLoading = ref(false);

/**
 * 我的家庭组额度。null = 还没拿到接口数据。
 *
 * ⚠️ **前端绝不能把 2 这个数字写进判断里**：额度是可配置的
 * （后端在 .env 里定义，将来会员还会按人加次数）。
 * 前端一旦写死，就会出现"后端说还能建、界面说不能"的自相矛盾。
 * 所以这里只做两件事：把后端给的数字显示出来，用它做判断。
 */
const rawQuota = ref<SpaceQuota | null>(null);
/** 给模板用的安全视图：没拿到数据时给一组空值，省得模板里到处判 null */
const quota = computed(() => rawQuota.value ?? { maxOwned: 0, maxJoined: 0, owned: 0, joined: 0 });
/** 额度数据是否已就绪——没就绪时不显示额度、也不说"已满" */
const hasQuota = computed(() => rawQuota.value !== null);

/** 额度是否已用满——决定"按钮还能不能点"和"要不要先把话说清楚" */
const createFull = computed(() => hasQuota.value && quota.value.owned >= quota.value.maxOwned);
const joinFull = computed(() => hasQuota.value && quota.value.joined >= quota.value.maxJoined);

/** 我创建的（创建人在自己组里的角色是 admin）／我加入的（角色是 member） */
const ownedSpaces = computed(() => spaces.value.filter((item) => item.myRole === 'admin'));
const joinedSpaces = computed(() => spaces.value.filter((item) => item.myRole !== 'admin'));

/** 两个分组的渲染数据：结构完全一样，卡片模板就只用写一遍 */
const sections = computed(() => [
  {
    key: 'owned',
    title: '我创建的',
    quotaText: `${ownedSpaces.value.length} / ${quota.value.maxOwned}`,
    full: createFull.value,
    emptyText: '还没有创建过家庭组',
    items: ownedSpaces.value,
  },
  {
    key: 'joined',
    title: '我加入的',
    quotaText: `${joinedSpaces.value.length} / ${quota.value.maxJoined}`,
    full: joinFull.value,
    emptyText: '还没有加入别人的家庭组',
    items: joinedSpaces.value,
  },
]);

const createDisabled = computed(
  () => pending.value || createFull.value || !createName.value.trim()
);
const joinDisabled = computed(() => pending.value || joinFull.value || !joinCode.value.trim());

/**
 * 列表里那行小字。
 *
 * 这里只写人数：分组标题已经说明了「我创建的 / 我加入的」，
 * 卡片里再重复一遍身份是多余的，人数才是用户在这里想知道的。
 *
 * 界面上统一说「创建人」而不是「管理员」：
 * 后端存的角色标识还是 admin（改字段成本高、没必要），
 * 但产品上不做"管理员"这套角色体系——只区分「创建人」和「普通成员」。
 */
function roleText(item: SpaceInfo): string {
  return `共 ${item.memberCount ?? 1} 人`;
}

/** 把页面上的"当前家庭"刷新成缓存里的值 */
function refreshCurrent(): void {
  currentId.value = getCurrentSpaceId();
  currentName.value = getCurrentSpaceName();
}

/** 加载列表（每次进入页面都刷新一次，保证看到的是最新的） */
async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    // 先确保登录态：首次进入或令牌过期时会自动登录，用户无感
    await ensureLogin();
    spaces.value = await resolveCurrentSpace();
    refreshCurrent();

    // 额度单独取：它失败了不该让整页报错——家庭组数据本身是好的，
    // 只是少显示一个"1 / 2"而已。
    try {
      rawQuota.value = await fetchSpaceQuota();
    } catch (quotaError) {
      // 保留上一次的额度（如果有），不打断页面
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取家庭组失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/**
 * 切换当前家庭组
 * @param silent 由创建/加入流程调用时传 true，避免和后面的提示重复弹两次
 */
function switchTo(item: SpaceInfo, silent = false): void {
  if (item.id === currentId.value) return;
  setCurrentSpace(item);
  refreshCurrent();
  if (!silent) uni.showToast({ title: `已切换到 ${item.name}`, icon: 'none' });
}

/** 复制邀请码：家人之间大多是复制粘贴分享 */
function copyCode(code?: string | null): void {
  if (!code) return;
  uni.setClipboardData({
    data: code,
    success: () => uni.showToast({ title: '邀请码已复制', icon: 'none' }),
    fail: () => uni.showToast({ title: '复制失败，请手动记录', icon: 'none' }),
  });
}

async function submitCreate(): Promise<void> {
  // 额度满了先把原因说清楚，而不是让用户填完名字才撞上一个错误提示。
  // 后端也会拦（而且后端才是真正的防线），这里只是把体验做顺。
  if (createFull.value) {
    uni.showModal({
      title: '已达上限',
      content: `您创建的家庭组数量已达上限（${quota.value.maxOwned} 个）。解散一个之后可以再创建。`,
      showCancel: false,
      confirmText: '知道了',
    });
    return;
  }

  const name = createName.value.trim();
  if (!name || pending.value) return;

  pending.value = true;
  try {
    const space = await createSpace(name);
    createName.value = '';
    creating.value = false;
    await load();
    // 刚创建的家庭组直接设为当前，用户马上就能开始用
    switchTo(space, true);
    uni.showToast({ title: `已创建「${space.name}」`, icon: 'none' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '创建失败，请重试', icon: 'none' });
  } finally {
    pending.value = false;
  }
}

async function submitJoin(): Promise<void> {
  // 同「创建」：先把原因说清楚再谈操作。
  // 这条提示同时也回答了"别人邀请我但他已经满了"的情况——
  // 加入只有"输邀请码"这一个入口，自己找的码和家人分享的码走的是同一条路。
  if (joinFull.value) {
    uni.showModal({
      title: '已达上限',
      content: `您加入的家庭组数量已达上限（${quota.value.maxJoined} 个）。退出一个之后可以再加入。`,
      showCancel: false,
      confirmText: '知道了',
    });
    return;
  }

  const code = joinCode.value.trim();
  if (!code || pending.value) return;

  pending.value = true;
  try {
    const space = await joinSpace(code);
    joinCode.value = '';
    joining.value = false;
    await load();
    switchTo(space, true);
    uni.showToast({ title: `已加入「${space.name}」`, icon: 'none' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '加入失败，请重试', icon: 'none' });
  } finally {
    pending.value = false;
  }
}

/** 拉取某个家庭组的成员列表 */
async function loadMembers(spaceId: string): Promise<void> {
  membersLoading.value = true;
  try {
    members.value = await fetchSpaceMembers(spaceId);
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '读取成员失败', icon: 'none' });
  } finally {
    membersLoading.value = false;
  }
}

/** 展开/收起成员管理面板（同一时间只展开一个） */
async function toggleMembers(item: SpaceInfo): Promise<void> {
  if (managingId.value === item.id) {
    managingId.value = null;
    return;
  }
  managingId.value = item.id;
  members.value = [];
  await loadMembers(item.id);
}

/**
 * 移除某个成员。
 *
 * 二次确认是必须的——这是别人看不见的破坏性操作，
 * 而且确认文案要说清代价（对方会失去对这个家的访问），不能只说"确定吗"。
 */
function confirmRemove(item: SpaceInfo, member: SpaceMember): void {
  uni.showModal({
    title: '移除成员',
    content: `确定把「${member.nickname || '该成员'}」移出「${item.name}」吗？对方将看不到这个家的菜谱和冰箱。`,
    confirmText: '移除',
    confirmColor: PRIMARY,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await removeSpaceMember(item.id, member.userId);
        uni.showToast({ title: '已移除', icon: 'none' });
        await loadMembers(item.id);
      } catch (error) {
        uni.showToast({ title: error instanceof Error ? error.message : '移除失败', icon: 'none' });
      }
    },
  });
}

/** 退出家庭组（创建人点不到这个按钮，后端也会再拦一道） */
function confirmLeave(item: SpaceInfo): void {
  uni.showModal({
    title: '退出家庭组',
    content: `确定退出「${item.name}」吗？退出后需要重新用邀请码加入。`,
    confirmText: '退出',
    confirmColor: PRIMARY,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await leaveSpace(item.id);
        managingId.value = null;
        await load();
        uni.showToast({ title: `已退出「${item.name}」`, icon: 'none' });
      } catch (error) {
        uni.showToast({ title: error instanceof Error ? error.message : '退出失败', icon: 'none' });
      }
    },
  });
}

/**
 * 解散家庭组。
 *
 * ⚠️ 这是本页唯一不可逆的操作：成员关系、菜谱、菜谱分类会**一起消失**。
 * 所以确认文案必须把"会删掉什么"讲出来，而不是一句干巴巴的"确定吗"。
 */
function confirmDissolve(item: SpaceInfo): void {
  uni.showModal({
    title: '解散家庭组',
    content: `「${item.name}」会被永久删除，里面的菜谱、分类和成员关系都会一并消失，且无法恢复。确定解散吗？`,
    confirmText: '解散',
    confirmColor: DANGER,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await dissolveSpace(item.id);
        managingId.value = null;
        await load();
        uni.showToast({ title: `已解散「${item.name}」`, icon: 'none' });
      } catch (error) {
        uni.showToast({ title: error instanceof Error ? error.message : '解散失败', icon: 'none' });
      }
    },
  });
}

onShow(load);
</script>

<style scoped>
.space-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.current-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.current-label { color: var(--c-text-2); font-size: 23rpx; }
.current-name { color: var(--c-text); font-size: 34rpx; font-weight: 500; }

.tip { display: block; margin-top: var(--s-5); color: var(--c-text-3); font-size: 24rpx; text-align: center; }

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
.error-hint { color: var(--c-text-2); font-size: 23rpx; line-height: 1.6; }
.retry-btn {
  align-self: flex-start;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 25rpx;
}

/* 分组：「我创建的」/「我加入的」。标题行右侧带额度用量 */
.section { margin-top: var(--s-4); }
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-2);
  margin: 0 var(--s-1) var(--s-2);
}
.group-title { color: var(--c-text-2); font-size: 23rpx; }
/* 额度用量（如 1 / 2）。满了转危险色——一眼看出"这里到顶了" */
.group-quota { color: var(--c-text-3); font-size: 23rpx; }
.group-quota.danger { color: var(--c-danger); font-weight: 500; }
/* 某个分组一个都没有时，给一句说明而不是留一片空白 */
.section-empty {
  display: block;
  padding: var(--s-4) var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  color: var(--c-text-3);
  font-size: 23rpx;
  text-align: center;
}

.space-item {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-bottom: var(--s-2);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
/* 选中态用主色描边 + 极浅底色，不用整块变色：
   整块变红会让"当前家庭"这条在列表里过于抢眼，反而干扰扫读 */
.space-item.selected { border-color: var(--c-primary); background: var(--c-primary-bg); }
.space-row { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); }
.space-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: var(--s-1); }
.space-name { color: var(--c-text); font-size: 30rpx; font-weight: 500; }
.space-meta { color: var(--c-text-2); font-size: 23rpx; }
.badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  height: 48rpx;
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 22rpx;
}

/* 整行可点（复制邀请码），高度给到 88rpx 以上，避免在手机上点不中 */
.invite-row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: var(--touch-min);
  padding: 0 var(--s-3);
  border-radius: var(--r-md);
  background: var(--c-muted);
}
.invite-label { color: var(--c-text-2); font-size: 23rpx; }
.invite-code {
  flex: 1;
  color: var(--c-text);
  font-size: 28rpx;
  font-weight: 500;
  letter-spacing: 2rpx;
}
.invite-action { color: var(--c-primary); font-size: 23rpx; font-weight: 500; }

/* 管理操作行：一行文字链，刻意做得比主信息轻，避免误触 */
.manage-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--s-3);
  margin-top: var(--s-1);
}
.manage-link {
  /* 文字本身不到 40rpx 高，远低于 88rpx 的可点下限。
     用「内边距撑大命中区 + 负外边距缩回」：视觉位置不变，
     手指能点到的面积却够大了——这是小文字链接的标准解法 */
  padding: 30rpx var(--s-2);
  margin: -30rpx calc(-1 * var(--s-2));
  color: var(--c-primary);
  font-size: 23rpx;
  font-weight: 500;
}
/* 解散是不可逆操作，用危险色区分，避免和「成员管理」看成一个层级 */
.manage-link.danger { color: var(--c-danger); }

/* 成员面板：浅底、缩进，视觉上明确属于上面那个家庭组 */
.member-panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-top: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-md);
  background: var(--c-muted);
}
.member-tip { color: var(--c-text-3); font-size: 22rpx; }
.member-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
  padding: var(--s-1) 0;
}
.member-main { display: flex; align-items: center; gap: var(--s-2); min-width: 0; }
.member-name {
  color: var(--c-text);
  font-size: 25rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.member-role {
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 20rpx;
  line-height: 32rpx;
}
/* 命中区同样用内边距 + 负外边距撑到 88rpx，视觉不变 */
.member-remove {
  padding: 30rpx var(--s-3);
  margin: -30rpx calc(-1 * var(--s-3));
  color: var(--c-danger);
  font-size: 23rpx;
  font-weight: 500;
}

.empty-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-top: var(--s-2);
  padding: var(--s-5) var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.empty-title { color: var(--c-text); font-size: 29rpx; font-weight: 500; }
.empty-copy { color: var(--c-text-2); font-size: 24rpx; line-height: 1.65; }

.action-card {
  margin-top: var(--s-2);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.action-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 104rpx;
  padding: 0 var(--s-3);
}
.action-name { color: var(--c-text); font-size: 28rpx; font-weight: 500; }
.action-sign { color: var(--c-primary); font-size: 23rpx; }
/* 额度标签 + 展开/收起，靠右排成一行 */
.action-tail { display: flex; align-items: center; gap: var(--s-2); }
.action-quota { color: var(--c-text-3); font-size: 23rpx; }
.action-quota.danger { color: var(--c-danger); font-weight: 500; }
/* 达上限时的说明：把原因摆在输入框上方，而不是让用户填完才被拒绝 */
.limit-hint { color: var(--c-danger); font-size: 23rpx; line-height: 1.6; }
.action-body { display: flex; flex-direction: column; gap: var(--s-2); padding: 0 var(--s-3) var(--s-3); }
.field {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 27rpx;
  box-sizing: border-box;
}
:deep(.field-placeholder) { color: var(--c-text-3); }
.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: #fff;
  font-size: 28rpx;
  font-weight: 500;
}
.submit-btn.disabled { background: var(--c-disabled); }

.page-note {
  display: block;
  margin-top: var(--s-4);
  color: var(--c-text-3);
  font-size: 22rpx;
  line-height: 1.7;
  text-align: center;
}
</style>
