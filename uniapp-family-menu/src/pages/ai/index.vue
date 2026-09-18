<template>
  <view class="ai-page">
    <view class="page-head">
      <text class="page-title">AI 助手</text>
      <text class="page-subtitle">说一句就记上</text>
    </view>

    <!-- 消息区：占满剩余高度，内部滚动。
         用原生 CSS overflow 而不是 scroll-view——本项目已全面弃用 scroll-view，
         它在重挂载时会抛 "scrollTop of null"（见项目记忆）。 -->
    <view class="chat">
      <!-- 空态：直接给可点的例子，比讲一堆用法强。
           点一下就直接发出去（不是只填进输入框）——否则用户不知道这个页面到底能干什么。 -->
      <view v-if="!messages.length" class="intro">
        <text class="intro-title">跟我说你吃了什么</text>
        <text class="intro-copy">我会整理成一条记录，你确认一下才真正记上。</text>
        <text class="intro-hint">点下面的例子就能试：</text>
        <view class="examples">
          <view
            v-for="e in EXAMPLES"
            :key="e"
            class="example"
            hover-class="tap"
            @click="sendExample(e)"
          >{{ e }}</view>
        </view>
      </view>

      <view v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <view class="bubble" :class="m.role">
          <text class="bubble-text">{{ m.content }}</text>

          <!-- 待确认的动作卡片：后端只给"草案"，点「记下」才真的写入。
               整块可点 → 打开详情弹层改数值（AI 从大白话里抽字段一定会错，得留个改的地方）。 -->
          <view v-for="(d, di) in m.drafts" :key="di" class="draft">
            <view class="draft-head" hover-class="tap" @click="openEditor(d)">
              <text class="draft-name">{{ d.food_name }}</text>
              <text v-if="d.done" class="draft-state">已记下</text>
              <text v-else-if="d.ignored" class="draft-state">已忽略</text>
              <!-- 已记下的也能改：改完会同步更新那条记录（见 saveEditor） -->
              <text v-if="!d.ignored" class="draft-edit">{{ d.done ? '改 ›' : '点这里改 ›' }}</text>
            </view>

            <view class="draft-meta" hover-class="tap" @click="openEditor(d)">
              <!-- 日期必须露出来：AI 把"昨天"记成昨天时，用户得能看见并确认 -->
              <text class="draft-date">{{ dateLabel(d.eaten_at) }}</text>
              <!-- 用户没说重量就不显示重量（后端给的 portion 为 null） -->
              <text v-if="d.portion" class="draft-portion">· {{ d.portion }}</text>
              <text v-if="d.calories !== null" class="draft-kcal">
                · {{ Math.round(d.calories) }} kcal
                <text v-if="d.calories_estimated" class="draft-tag">估算</text>
              </text>
              <text v-else class="draft-kcal empty">· 未填热量</text>
            </view>

            <view v-if="!d.done && !d.ignored" class="draft-actions">
              <view class="draft-btn primary" hover-class="tap" @click="confirmDraft(d)">记下</view>
              <view class="draft-btn ghost" hover-class="tap" @click="d.ignored = true">忽略</view>
            </view>
          </view>
        </view>
      </view>

      <view v-if="busy" class="msg assistant">
        <view class="bubble assistant typing">思考中…</view>
      </view>
    </view>

    <!-- 底部浮层：整体固定在 tabBar 之上。
         ⚠️ 必须用 position:fixed 并显式让过 tabBar（约 120rpx）+ 安全区，
         否则会被压在 tabBar 底下点不到——这是本项目的既有做法，
         见 pages/menu/index.vue 的 .cart-bar（那里有同样的注释）。 -->
    <view class="bottom-bar">
      <!-- 没配 Key 时后端会回占位回复，这里如实说明，别让用户以为记上了 -->
      <view v-if="mock" class="mock-hint">
        演示数据：把可用的 DashScope Key 填进后端 .env 即自动接通真实对话
      </view>

      <view v-if="todayCount > 0" class="today">
        <text class="today-label">今天已记</text>
        <text class="today-value">{{ todayCount }} 条 · {{ Math.round(todayTotal) }} kcal</text>
      </view>

      <view class="composer">
        <input
          v-model="draftText"
          class="composer-input"
          placeholder="比如：中午吃了红烧肉500g，550kcal"
          placeholder-class="field-placeholder"
          confirm-type="send"
          :disabled="busy"
          @confirm="send"
        />
        <view
          class="composer-send"
          :class="{ disabled: !canSend }"
          hover-class="tap"
          @click="send"
        >发送</view>
      </view>
    </view>

    <!-- 详情编辑弹层：AI 抽错的字段在这里改。
         编辑的是**副本**（form），点「取消」不会污染卡片上的原值。 -->
    <view v-if="editing" class="edit-mask" @click="closeEditor">
      <view class="edit-dialog" @click.stop>
        <text class="edit-title">修改这条记录</text>
        <text class="edit-hint">
          {{ editing.done ? '改完点保存，已记下的那条会同步更新' : 'AI 听错的地方直接改，改完点保存' }}
        </text>

        <view class="edit-field">
          <text class="edit-label">日期</text>
          <picker mode="date" :value="form.eaten_at" @change="onDateChange">
            <view class="edit-picker">{{ dateLabel(form.eaten_at) }}（{{ form.eaten_at }}）</view>
          </picker>
        </view>

        <view class="edit-field">
          <text class="edit-label">餐品名称</text>
          <input
            v-model="form.food_name"
            class="edit-input"
            placeholder="如 红烧肉"
            placeholder-class="field-placeholder"
            :maxlength="64"
          />
        </view>

        <view class="edit-field">
          <text class="edit-label">份量</text>
          <input
            v-model="form.portion"
            class="edit-input"
            placeholder="如 500g / 一碗（留空就不显示）"
            placeholder-class="field-placeholder"
            :maxlength="64"
          />
        </view>

        <view class="edit-field">
          <text class="edit-label">热量（kcal）</text>
          <input
            v-model="form.calories"
            class="edit-input"
            type="digit"
            placeholder="如 550"
            placeholder-class="field-placeholder"
          />
        </view>

        <view class="edit-actions">
          <view class="edit-cancel" hover-class="tap" @click="closeEditor">取消</view>
          <view class="edit-confirm" hover-class="tap" @click="saveEditor">保存</view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
/**
 * AI 助手 tab —— 目前落地的是「用一句话记账」。
 *
 * 一轮的流程：
 *   用户说一句 → 后端模型整理成「回复 + 动作草案」→ 这里渲染成气泡 + 确认卡片
 *   → 用户点「记下」→ 调**已有的** addCalorieLog 写进热量记录（source='ai_text'）。
 *
 * ⚠️ 三条必须守住的规则：
 *   1. **绝不自动写入**。AI 只负责提议，写入永远要用户点一下确认——
 *      模型从大白话里抽字段一定会错，卡在它前面比事后清库便宜。
 *   2. **用户没说重量就不显示重量**（后端 portion 为 null，这里就不渲染那一段）。
 *   3. **热量是模型估的要标「估算」**，别让用户以为那是他自己说的数。
 *
 * 卡片可编辑（点任意位置打开详情弹层，改日期/名称/份量/热量）：
 *   · 还没记下 → 只改卡片上的值，写库仍然只有「记下」那一个入口。
 *   · 已记下   → 调 PUT 回写那条记录（`logId` 就是记下时存下来的主键）。
 *     这一步必须写库：用户往往在记完以后才发现 AI 抽错了，
 *     只改界面的话就会"界面 550、库里 650"两张皮。
 *
 * 日期一定要显示出来：AI 会把"昨天吃的"正确记成昨天，
 * 但用户看不见这个字段就没法确认，所以卡片上露出来、弹层里也能改。
 *
 * 拍照识别热量已从本页移除（用户定的：先专心把对话做好）。后端
 * /vision/recognize-food 保留未动，将来想恢复随时接回来。
 *
 * 历史消息本轮只存内存，关掉页面就没了；每次请求回填最近几轮，让"再加一碗"能懂。
 */

import { computed, nextTick, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import { sendAiMessage, type ActionDraft, type AiChatTurn } from '../../services/ai-chat';
import { addCalorieLog, fetchCalorieLogs, updateCalorieLog, type CalorieLog } from '../../services/health';
import { getCurrentSpaceId } from '../../utils/space-context';
import { hasValidToken } from '../../utils/token';
import { showError } from '../../utils/format';

/** 空态里给的可点例子：让用户一眼知道可以怎么说话 */
const EXAMPLES = [
  '中午吃了红烧肉500g，550kcal',
  '刚吃了个苹果',
  '晚饭吃了红烧排骨，600千卡',
];
/** 回填给后端的历史轮数上限（和后端 MAX_HISTORY_TURNS 对齐） */
const MAX_HISTORY = 6;

/** 卡片上的草案：在后端结构上加了几个纯界面状态 */
interface ChatDraft extends ActionDraft {
  /** 已写入记录 */
  done: boolean;
  /** 用户点了忽略 */
  ignored: boolean;
  /** 已写入记录的主键。有了它，「已记下」的卡片再改就能回写数据库（而不是只改界面） */
  logId: number | null;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  drafts: ChatDraft[];
}

const messages = ref<ChatMessage[]>([]);
const draftText = ref('');
const busy = ref(false);
/** 后端是否返回了占位数据（没配 Key） */
const mock = ref(false);

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

/**
 * 卡片上的日期显示：今天 / 昨天 / 9月16日。
 *
 * 为什么一定要显示？AI 说"昨天吃的"时会把日期记成昨天（这是对的），
 * 但用户看不见这个字段就没法确认它记对了——所以日期必须露出来，而且要能改。
 */
function dateLabel(iso: string): string {
  if (iso === todayStr()) return '今天';
  const d = new Date(`${todayStr()}T00:00:00`);
  d.setDate(d.getDate() - 1);
  const yesterday = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  if (iso === yesterday) return '昨天';
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  return `${Number(parts[1])}月${Number(parts[2])}日`;
}

const canSend = computed(() => !busy.value && draftText.value.trim().length > 0);

/** 拉当天累计（拉不到就维持空态，不打断对话） */
async function loadToday(): Promise<void> {
  if (!hasValidToken()) return;
  try {
    logs.value = await fetchCalorieLogs();
  } catch {
    // 后端没启动/网络不通时不弹错，避免干扰正在进行的对话
  }
}

onShow(loadToday);

/** 点例子：**直接发出去**。
 *  只把它填进输入框的话，用户根本不知道这一页能干什么——他要的是看到效果。 */
function sendExample(text: string): void {
  draftText.value = text;
  void send();
}

/** 滚到最新一条。页面整体是自然滚动的（底部输入框用 fixed 浮在上面），
 *  消息变长后不滚的话，新一轮的回复会藏在输入框后面。 */
async function scrollToBottom(): Promise<void> {
  await nextTick();
  uni.pageScrollTo({ scrollTop: 999999, duration: 200 });
}

/** 把内存里的消息转成后端要的历史（只带最近几轮） */
function buildHistory(): AiChatTurn[] {
  return messages.value.slice(-MAX_HISTORY).map((m) => ({ role: m.role, content: m.content }));
}

/** 发一句话 */
async function send(): Promise<void> {
  if (!canSend.value) return;
  const text = draftText.value.trim();
  if (!text) return;

  try {
    await ensureLogin();
  } catch {
    return;
  }

  const history = buildHistory();
  messages.value.push({ role: 'user', content: text, drafts: [] });
  draftText.value = '';
  busy.value = true;
  await scrollToBottom();

  try {
    const resp = await sendAiMessage(text, history, getCurrentSpaceId() || undefined);
    mock.value = resp.mock;
    messages.value.push({
      role: 'assistant',
      content: resp.reply,
      drafts: resp.actions.map((a) => ({ ...a, done: false, ignored: false, logId: null })),
    });
  } catch (error) {
    showError(error);
    // 出错时把用户那句话留在列表里，方便他复制重发；同时给一句失败的回应
    messages.value.push({ role: 'assistant', content: '刚才没处理过来，再说一次试试？', drafts: [] });
  } finally {
    busy.value = false;
  }
  await scrollToBottom();
}

/* ---------------- 详情编辑弹层 ---------------- */

/** 正在编辑的草案（null = 弹层没开） */
const editing = ref<ChatDraft | null>(null);

/** 弹层里的表单副本。
 *  编辑副本而不是直接绑原对象——点「取消」时不能把卡片上的原值改坏。 */
const form = ref({ food_name: '', portion: '', calories: '', eaten_at: '' });

/**
 * 打开详情编辑。
 *
 * **「已记下」的卡片也允许打开**：AI 抽错是常态，而用户往往是在记完以后才看出来的。
 * 这时改完必须**回写那条记录**（见 saveEditor），不能只改界面——
 * 否则界面显示 550、数据库里还留着 650，两张皮。
 * 只有「已忽略」的不再管（用户已经把它丢弃了）。
 */
function openEditor(d: ChatDraft): void {
  if (d.ignored) return;
  editing.value = d;
  form.value = {
    food_name: d.food_name,
    portion: d.portion ?? '',
    calories: d.calories === null ? '' : String(Math.round(d.calories)),
    eaten_at: d.eaten_at,
  };
}

function closeEditor(): void {
  editing.value = null;
}

function onDateChange(e: { detail: { value: string } }): void {
  form.value.eaten_at = e.detail.value;
}

/**
 * 保存编辑。
 *
 * 两条分支：
 *   · 还没记下 → 只改卡片上的值，等用户点「记下」再写库（写库始终只有那一个入口）。
 *   · 已记下   → 调 PUT 回写那条记录；**写库失败就不改界面**，避免界面与记录不一致。
 */
async function saveEditor(): Promise<void> {
  const target = editing.value;
  if (!target) return;

  const name = form.value.food_name.trim();
  if (!name) {
    uni.showToast({ title: '餐品名称不能为空', icon: 'none' });
    return;
  }

  const kcal = Number(form.value.calories.trim());
  if (!Number.isFinite(kcal) || kcal <= 0 || kcal > 10000) {
    uni.showToast({ title: '热量请填 0–10000 之间的数字', icon: 'none' });
    return;
  }

  const portion = form.value.portion.trim();
  const next = {
    food_name: name.slice(0, 64),
    // 份量留空就是 null —— 和"用户没说重量就不显示重量"是同一条规则
    portion: portion ? portion.slice(0, 64) : null,
    calories: Math.round(kcal),
    eaten_at: form.value.eaten_at,
  };

  if (target.done) {
    if (target.logId === null) {
      uni.showToast({ title: '这条记录的编号丢了，请刷新后重试', icon: 'none' });
      return;
    }
    try {
      await updateCalorieLog(target.logId, next);
    } catch (error) {
      // 写库失败 → 界面保持原样，别让用户以为改成功了
      showError(error);
      return;
    }
    await loadToday();
  }

  const kcalChanged = next.calories !== target.calories;
  target.food_name = next.food_name;
  target.portion = next.portion;
  target.calories = next.calories;
  target.eaten_at = next.eaten_at;
  // 用户自己改过热量，那它就不再是"模型估算"了——「估算」这个标签必须摘掉，
  // 否则界面在说假话（明明是用户填的，还标着估算）。
  if (kcalChanged) target.calories_estimated = false;

  editing.value = null;
  uni.showToast({ title: target.done ? '已更新记录' : '已保存', icon: 'none' });
}

/** 点「记下」：真正写库的一步，走的是已有的热量记录接口 */
async function confirmDraft(d: ChatDraft): Promise<void> {
  const kcal = d.calories;
  if (kcal === null) {
    uni.showToast({ title: '先点卡片把热量填上', icon: 'none' });
    return;
  }
  if (!Number.isFinite(kcal) || kcal <= 0 || kcal > 10000) {
    uni.showToast({ title: '热量请填 0–10000 之间的数字', icon: 'none' });
    return;
  }

  try {
    const created = await addCalorieLog({
      food_name: d.food_name,
      calories: Math.round(kcal),
      // 用户没说重量就传 null —— 记录里不会凭空多出一个份量
      portion: d.portion,
      eaten_at: d.eaten_at,
      source: 'ai_text',
    });
    // 记住主键：之后用户再点卡片改，要靠它回写这条记录
    d.logId = created.id;
    d.done = true;
    uni.showToast({ title: '已记下', icon: 'success' });
    await loadToday();
  } catch (error) {
    showError(error);
  }
}
</script>

<style scoped>
/* ⚠️ 页面走**自然滚动**，不再用 flex + 100vh 钉底。
   原因：底部输入框用 flex 钉在 100vh 的末端时，会被 tabBar 压住点不到
   （tabBar 是页面容器之外的一层）。本项目的做法是——底部控件用 position:fixed
   并显式让过 tabBar，见 pages/menu/index.vue 的 .cart-bar。
   所以这里给页面留出底部浮层的高度，别让最后一条消息被盖住。 */
.ai-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: var(--s-4) var(--s-3) calc(200rpx + env(safe-area-inset-bottom));
  background: var(--c-bg);
}

/* 页头：不加边框和底——它是"页面身份"，不是卡片 */
.page-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}
.page-title {
  overflow: hidden;
  color: var(--c-text);
  font-size: 40rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.page-subtitle { flex: 0 0 auto; color: var(--c-text-2); font-size: 23rpx; }

.chat { padding: var(--s-3) 0 0; }

/* ---------- 空态 ---------- */
.intro { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-5) var(--s-2); }
.intro-title { color: var(--c-text); font-size: 30rpx; font-weight: 500; }
.intro-copy { color: var(--c-text-2); font-size: 24rpx; line-height: 1.7; }
.intro-hint { color: var(--c-text-3); font-size: 23rpx; }
.examples { display: flex; flex-direction: column; gap: var(--s-2); margin-top: var(--s-2); }
.example {
  align-self: flex-start;
  display: flex;
  align-items: center;
  min-height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-pill);
  color: var(--c-text-2);
  font-size: 24rpx;
}

/* ---------- 消息气泡 ---------- */
.msg { display: flex; margin-bottom: var(--s-3); }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }

.bubble {
  max-width: 84%;
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-lg);
  box-sizing: border-box;
}
.bubble.user { background: var(--c-primary-bg); border: 2rpx solid var(--c-primary-border); }
.bubble.assistant {
  background: var(--c-surface);
  border: 2rpx solid var(--c-border);
  box-shadow: var(--shadow-card);
}
.bubble-text { color: var(--c-text); font-size: 27rpx; line-height: 1.6; }
.bubble.typing { color: var(--c-text-3); font-size: 25rpx; }

/* ---------- 确认卡片 ---------- */
.draft {
  margin-top: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border: 2rpx solid var(--c-primary-border);
  border-radius: var(--r-md);
  background: var(--c-primary-bg);
}
.draft-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-2); }
.draft-name { color: var(--c-text); font-size: 28rpx; font-weight: 500; }
.draft-state { flex: 0 0 auto; color: var(--c-text-3); font-size: 22rpx; }
/* 「点这里改 ›」：卡片可编辑的提示。用主色、给足触摸高度（本来就是整行可点） */
.draft-edit {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  min-height: 56rpx;
  padding-left: var(--s-3);
  color: var(--c-primary);
  font-size: 22rpx;
}
/* 头部（含「点这里改」）与这行合起来就是一个够大的点按区，所以不给它单独撑高——
   卡片保持紧凑更重要。 */
.draft-meta { display: flex; align-items: center; flex-wrap: wrap; gap: var(--s-2); margin-top: var(--s-1); }
.draft-date { color: var(--c-text-2); font-size: 23rpx; }
.draft-portion { color: var(--c-text-2); font-size: 23rpx; }
.draft-kcal { color: var(--c-primary); font-size: 26rpx; font-weight: 500; }
/* 「估算」标签：热量是模型估的时候必须标出来，别让用户以为是自己的数 */
.draft-tag {
  margin-left: var(--s-1);
  padding: 2rpx var(--s-1);
  border-radius: var(--r-sm);
  background: var(--c-warn-bg);
  color: var(--c-warn-text);
  font-size: 20rpx;
  font-weight: 400;
}
/* 热量还没填：用弱化的文字提示，不再是内联输入框——
   改数值统一走详情弹层，只有一个编辑入口，不会两处各说各话。 */
.draft-kcal.empty { color: var(--c-text-3); font-weight: 400; }
.draft-actions { display: flex; gap: var(--s-2); margin-top: var(--s-2); }
.draft-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  font-size: 25rpx;
}
.draft-btn.primary { background: var(--c-primary); color: #fff; font-weight: 500; }
.draft-btn.ghost { border: 2rpx solid var(--c-border-strong); color: var(--c-text-2); }

/* ---------- 底部浮层（提示 + 当日累计 + 输入框） ---------- */
/* ⚠️ bottom 必须让过 tabBar（约 120rpx）+ 全面屏手势条（安全区），
   少让一样就会在某个机型上被压在 tabBar 底下点不到。
   这是本项目的既有做法，见 pages/menu/index.vue 的 .cart-bar。 */
.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: calc(120rpx + env(safe-area-inset-bottom));
  z-index: 20;
  /* ⚠️ 必须 border-box：left/right:0 + 左右 padding 时，content-box 会让
     实际宽度 = 100% + padding，整条溢出到屏幕外，"发送"按钮就被挤出可视区了。 */
  box-sizing: border-box;
  padding: 0 var(--s-3);
  background: var(--c-bg);
}

.mock-hint {
  margin-bottom: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-muted);
  color: var(--c-text-2);
  font-size: 22rpx;
  line-height: 1.5;
}
.today {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-primary-bg);
}
.today-label { color: var(--c-text-2); font-size: 23rpx; }
.today-value { color: var(--c-primary); font-size: 27rpx; font-weight: 500; }

/* ---------- 输入区 ---------- */
.composer {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) 0;
  border-top: 2rpx solid var(--c-border);
}
.composer-input {
  flex: 1;
  min-width: 0;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 26rpx;
  box-sizing: border-box;
}
.composer-send {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 26rpx;
  font-weight: 500;
}
.composer-send.disabled { background: var(--c-disabled); color: #fff; }

/* ---------- 详情编辑弹层 ----------
   沿用 menu 页辣度弹层那套（居中卡片 + 半透明遮罩），全站弹层观感一致。 */
.edit-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56rpx 44rpx;
  background: rgba(28, 25, 23, 0.48);
  box-sizing: border-box;
}
.edit-dialog {
  width: 100%;
  max-width: 620rpx;
  padding: var(--s-4) var(--s-3);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: 0 16rpx 40rpx rgba(28, 25, 23, 0.22);
  box-sizing: border-box;
}
.edit-title { display: block; color: var(--c-text); font-size: 34rpx; font-weight: 500; }
.edit-hint { display: block; margin-top: 6rpx; color: var(--c-text-2); font-size: 24rpx; }
.edit-field { display: flex; flex-direction: column; gap: var(--s-1); margin-top: var(--s-3); }
.edit-label { color: var(--c-text-2); font-size: 24rpx; }
.edit-input,
.edit-picker {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 28rpx;
  box-sizing: border-box;
}
/* picker 里放的是 view，不是 input，得自己撑成一行并垂直居中 */
.edit-picker { display: flex; align-items: center; }
.edit-actions { display: flex; gap: var(--s-2); margin-top: var(--s-4); }
.edit-cancel,
.edit-confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  border-radius: var(--r-md);
  font-size: 28rpx;
}
.edit-cancel {
  flex: 0 0 200rpx;
  border: 2rpx solid var(--c-border-strong);
  background: var(--c-surface);
  color: var(--c-text-2);
}
.edit-confirm {
  flex: 1;
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}
</style>
