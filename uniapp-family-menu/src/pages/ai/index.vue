<template>
  <view class="ai-page">
    <!-- 顶部只留一条细工具条（2026-09-19 重排）。
         ⚠️ 这里**不再重复写「AI 助手」**——原生导航栏已经有这个标题了，
         页内再写一遍等于同一句话说两遍，还把首屏顶掉 53px（用户反馈"太臃肿"）。
         换成放**真有用的状态**：今天记了几条；没记录时就是一句引导。
         底部那条也因此瘦身：只留输入框，不再叠一张"今天已记"的卡片。 -->
    <view class="page-bar">
      <text v-if="todayCount > 0" class="bar-stat">
        今天已记 <text class="bar-num">{{ todayCount }}</text> 条 ·
        {{ Math.round(todayTotal) }} kcal
      </text>
      <text v-else class="bar-stat">说一句就记上</text>
      <!-- 新对话：清空后端历史。有过对话才显示，空态里点了也没意义 -->
      <view v-if="messages.length" class="head-btn" hover-class="tap" @click="startNewChat">
        新对话
      </view>
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

          <!-- AI 的查询过程：把"它真的去看了"亮出来。
               ⚠️ 为什么值得占一行：AI 现在会自己去查冰箱和菜单，
                  只显示最后那句话的话，用户会觉得"它怎么知道我冰箱里有什么"。
                  空数组（闲聊）不显示——那本身也是个信息，但没必要专门说一句。 -->
          <view v-if="m.steps && m.steps.length" class="trace">
            <view v-for="(s, si) in m.steps" :key="si" class="trace-row">
              <text class="trace-dot" :class="s.ok ? 'ok' : 'fail'"></text>
              <text class="trace-text">{{ toolLabel(s.tool) }} · {{ s.detail }}</text>
            </view>
          </view>

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
                <!-- 来源标签：这个数字是"查到的"还是"估的"，必须让用户看得见。
                     以前只有「估算」一种，现在分三档（见 sourceLabel）。 -->
                <text v-if="sourceLabel(d)" class="draft-tag" :class="sourceTagClass(d)">
                  {{ sourceLabel(d) }}
                </text>
              </text>
              <text v-else class="draft-kcal empty">· 未填热量</text>
            </view>

            <view v-if="!d.done && !d.ignored && !d.mock" class="draft-actions">
              <view class="draft-btn primary" hover-class="tap" @click="confirmDraft(d)">记下</view>
              <view class="draft-btn ghost" hover-class="tap" @click="d.ignored = true">忽略</view>
            </view>
          </view>
        </view>
      </view>

      <view v-if="busy" class="msg assistant">
        <view class="bubble assistant typing">
          <text>思考中…</text>
          <!-- 流式步骤（SSE）：AI 每查完一个工具就当场亮出来。
               等待总时长没变，但"看得见的进度"和干等转圈完全是两种体感。 -->
          <view v-if="liveSteps.length" class="trace live">
            <view v-for="(s, si) in liveSteps" :key="si" class="trace-row">
              <text class="trace-dot" :class="s.ok ? 'ok' : 'fail'"></text>
              <text class="trace-text">{{ toolLabel(s.tool) }} · {{ s.detail }}</text>
            </view>
          </view>
        </view>
      </view>

      <view v-if="recognizing" class="msg assistant">
        <view class="bubble assistant typing">正在识别照片，仅用于本次识别…</view>
      </view>
    </view>

    <!-- 底部浮层：整体固定在 tabBar 之上。
         ⚠️ bottom 分平台写（H5 让过 DOM tabBar，App 是原生 tabBar 不占页面区域），
         见本文件 .bottom-bar 的样式注释与 .cart-bar 的同一处坑。
         2026-09-19 瘦身：原来这里还叠着一张"今天已记"的卡片，
         现已上移到顶部工具条——输入区只该有输入框。 -->
    <view class="bottom-bar">
      <!-- 没配 Key 时后端会回占位回复，这里如实说明，别让用户以为记上了 -->
      <view v-if="mock" class="mock-hint">
        演示数据：把可用的 DashScope Key 填进后端 .env 即自动接通真实对话
      </view>

      <view class="composer">
        <view
          class="composer-photo"
          :class="{ disabled: busy || recognizing }"
          hover-class="tap"
          @click="chooseFoodPhoto"
        >{{ recognizing ? '识别中' : '拍照' }}</view>
        <input
          v-model="draftText"
          class="composer-input"
          placeholder="比如：中午吃了红烧肉500g，550kcal"
          placeholder-class="field-placeholder"
          confirm-type="send"
          :disabled="busy || recognizing"
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
 * 拍照识别只生成待确认草案，只有用户确认后才写入热量记录；演示结果不可写入。
 *
 * 对话历史（2026-09-18 起）：
 *   **存在后端**（ai_chat_messages 表），上下文也由后端自己取——前端不再传 history，
 *   刷新/换设备都不断片。进页面拉一次最近 50 条回放；「新对话」清空后端历史重新开始。
 *   ⚠️ 回放**只渲染文本气泡、不渲染确认卡片**：卡片的「已记下」是本地状态，
 *   回放卡片会诱导用户对着已记过的菜再点一次「记下」→ 重复记录。
 */

import { computed, nextTick, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import {
  clearAiMessages,
  fetchAiMessages,
  sendAiMessageStream,
  type ActionDraft,
  type AgentStepInfo,
} from '../../services/ai-chat';
import { addCalorieLog, fetchCalorieLogs, recognizeFoodImage, updateCalorieLog, type CalorieLog } from '../../services/health';
import { chooseImageFromAlbum } from '../../services/upload';
import { getCurrentSpaceId } from '../../utils/space-context';
import { hasValidToken } from '../../utils/token';
import { showError } from '../../utils/format';

/** 空态里给的可点例子：让用户一眼知道可以怎么说话。
 *
 * ⚠️ 2026-09-21 加了后两条：AI 现在能**自己去查冰箱和菜单**了，
 *    光放"记账"的例子，用户根本不知道它还会这个。
 *    例子点一下就直接发出去（不是只填进输入框），这样用户立刻能看到
 *    "它真的去查了"（气泡下面会显示查了什么）。 */
const EXAMPLES = [
  '中午吃了红烧肉500g，550kcal',
  '刚吃了个苹果',
  '我冰箱里还有什么',
  '今天吃什么好',
];

/** 卡片上的草案：在后端结构上加了几个纯界面状态 */
interface ChatDraft extends ActionDraft {
  /** 已写入记录 */
  done: boolean;
  /** 用户点了忽略 */
  ignored: boolean;
  /** 已写入记录的主键。有了它，「已记下」的卡片再改就能回写数据库（而不是只改界面） */
  logId: number | null;
  /** 记录写入来源；区别于热量可信度 source。 */
  recordSource?: string;
  /** 后端未配置视觉模型时返回的占位结果，只能查看，不能记入正式记录。 */
  mock?: boolean;
}

/** 热量来源标签（可信度分级）。
 *
 * ⭐ 这是这次改造在界面上的落点：以前热量全是模型估的，
 *    同一个红烧肉今天 400 明天 520，用户既看不出是估的、也无从判断准不准。
 *    现在后端会告诉我们这个数是怎么来的，就如实标出来。
 *
 * 取值由后端定（见 app/schemas/ai_chat.py 的 ActionDraft.source）：
 *   mcp_exact    —— 和权威数据源精确对上了
 *   mcp_derived  —— 查到了主料，但按烹饪方式做了修正
 *   llm_estimate —— 纯模型估算
 */
const SOURCE_LABELS: Record<string, string> = {
  mcp_exact: '已核对',
  mcp_derived: '按主料推算',
  llm_estimate: '估算',
};

/** 工具名 → 给人看的说法（后端给的是英文函数名）。 */
const TOOL_LABELS: Record<string, string> = {
  list_fridge_items: '查冰箱',
  get_expiring_items: '查临期',
  list_recipes: '查菜单',
  list_categories: '查分类',
  lookup_nutrition: '查热量',
};

function toolLabel(tool: string): string {
  // 认不出来就原样显示——总比什么都不显示好，也方便我们发现后端加了新工具
  return TOOL_LABELS[tool] ?? tool;
}

/** 算这一条该显示什么来源标签；空字符串 = 不显示。
 *
 * ⚠️ 用户自己改过热量之后就不该再标来源了（那时数字是用户填的），
 *    所以 saveEditor 里会把 source 清空，这里跟着就不显示了。
 */
function sourceLabel(d: ChatDraft): string {
  if (!d.source) {
    // 兜底：老数据可能没有 source 字段，退回按"是不是估的"判断
    return d.calories_estimated ? '估算' : '';
  }
  return SOURCE_LABELS[d.source] ?? '';
}

/** 来源标签的配色。三档用三种颜色，让用户**一眼分出可信度**：
 *  绿=已核对（最好的）／蓝绿=按主料推算（有依据但不精确）／琥珀=纯估算（提醒）*/
function sourceTagClass(d: ChatDraft): string {
  if (d.source === 'mcp_exact') return 'exact';
  if (d.source === 'mcp_derived') return 'derived';
  return '';
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  drafts: ChatDraft[];
  /** 这一轮 AI 调用了哪些工具（查冰箱/查菜单/查热量）。
   *  用户消息永远是空数组；助手消息里空数组表示"它一次都没查"（闲聊）。 */
  steps: AgentStepInfo[];
}

const messages = ref<ChatMessage[]>([]);
const draftText = ref('');
const busy = ref(false);
const recognizing = ref(false);
/** 本轮已收到的流式步骤（SSE 实时推来的），回复出来后清空 */
const liveSteps = ref<AgentStepInfo[]>([]);
/** 后端是否返回了占位数据（没配 Key） */
const mock = ref(false);
/** 历史是否已经拉过。只拉一次：之后 onShow 再触发也不重放，
 *  否则切个 tab 回来就把还没处理的确认卡片冲掉了 */
const historyLoaded = ref(false);

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

onShow(() => {
  void loadToday();
  void loadHistory();
});

/** 拉后端的对话历史回放（每次会话只拉一次，见 historyLoaded 的说明）。
 *  失败静默：拉不到历史只影响"看不到上次的对话"，不该弹错误打断使用。 */
async function loadHistory(): Promise<void> {
  if (historyLoaded.value || !hasValidToken()) return;
  historyLoaded.value = true;
  try {
    const rows = await fetchAiMessages();
    messages.value = rows.map((row) => ({
      role: row.role,
      content: row.content,
      drafts: [], // 历史不回放确认卡片，理由见文件头的说明
      steps: [], // 历史也不回放"查了什么"——它是当轮的过程，翻上去看反而干扰
    }));
    if (rows.length) await scrollToBottom();
  } catch {
    // 保持空态即可，空态里有可点的示例，不碍事
  }
}

/** 「新对话」：清空后端历史，上下文从头开始。
 *  二次确认不能省——点掉就找不回来了。 */
function startNewChat(): void {
  if (busy.value) return;
  uni.showModal({
    title: '开始新对话',
    content: '会清空这里的聊天记录，AI 也会忘记之前聊的内容。要继续吗？',
    confirmText: '清空',
    success: async (result) => {
      if (!result.confirm) return;
      try {
        await clearAiMessages();
        messages.value = [];
        mock.value = false;
      } catch (error) {
        showError(error);
      }
    },
  });
}

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

/** 发一句话（上下文由后端自己取，前端只管把这句话递过去） */
async function send(): Promise<void> {
  if (!canSend.value || recognizing.value) return;
  const text = draftText.value.trim();
  if (!text) return;

  try {
    await ensureLogin();
  } catch {
    return;
  }

  messages.value.push({ role: 'user', content: text, drafts: [], steps: [] });
  draftText.value = '';
  busy.value = true;
  liveSteps.value = [];
  await scrollToBottom();

  try {
    // 流式：步骤实时亮出来；链路不可用时内部自动回落一次性接口
    // （回落条件见 sendAiMessageStream——业务错误不回落，避免重复扣额度）
    const resp = await sendAiMessageStream(text, getCurrentSpaceId() || undefined, (s) => {
      liveSteps.value.push(s);
      void scrollToBottom();
    });
    mock.value = resp.mock;
    messages.value.push({
      role: 'assistant',
      content: resp.reply,
      drafts: resp.actions.map((a) => ({ ...a, done: false, ignored: false, logId: null })),
      steps: resp.steps ?? [],
    });
  } catch (error) {
    showError(error);
    // 出错时把用户那句话留在列表里，方便他复制重发；同时给一句失败的回应
    messages.value.push({
      role: 'assistant',
      content: '刚才没处理过来，再说一次试试？',
      drafts: [],
      steps: [],
    });
  } finally {
    busy.value = false;
    liveSteps.value = [];
  }
  await scrollToBottom();
}

/** 拍照或从相册选图识别；图片通过 multipart 直接发送到后端内存处理，不留服务器文件。 */
async function chooseFoodPhoto(): Promise<void> {
  if (busy.value || recognizing.value) return;
  try {
    await ensureLogin();
    const filePath = await chooseImageFromAlbum();
    recognizing.value = true;
    const result = await recognizeFoodImage(filePath);
    if (!result.items.length) {
      uni.showToast({ title: '没有识别到食物，请换张照片试试', icon: 'none' });
      return;
    }

    const drafts: ChatDraft[] = result.items.map((item) => ({
      kind: 'create_calorie_log',
      food_name: item.food_name,
      portion: item.portion,
      calories: item.calories > 0 ? item.calories : null,
      calories_estimated: true,
      eaten_at: todayStr(),
      source: 'llm_estimate',
      recordSource: 'vision',
      mock: result.mock,
      matched_food: null,
      done: false,
      ignored: false,
      logId: null,
    }));
    messages.value.push({
      role: 'user',
      content: '我拍了一张食物照片，请帮我识别。',
      drafts: [],
      steps: [],
    });
    messages.value.push({
      role: 'assistant',
      content: result.mock ? '这是演示占位结果，不会写入记录；配置视觉模型后才能识别真实食物。' : '识别完成，请核对食物名称和热量，确认后才会保存。',
      drafts,
      steps: [],
    });
    await scrollToBottom();
  } catch (error) {
    if (error instanceof Error && !/取消|cancel/i.test(error.message)) showError(error);
  } finally {
    recognizing.value = false;
  }
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
  if (d.mock) {
    uni.showToast({ title: '演示占位结果不能编辑', icon: 'none' });
    return;
  }
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
  // 用户自己改过热量，那它就不再是"模型估算"了——来源标签必须摘掉，
  // 否则界面在说假话（明明是用户填的，还标着「估算」/「按主料推算」）。
  if (kcalChanged) {
    target.calories_estimated = false;
    target.source = '';
  }

  editing.value = null;
  uni.showToast({ title: target.done ? '已更新记录' : '已保存', icon: 'none' });
}

/** 点「记下」：真正写库的一步，走的是已有的热量记录接口 */
async function confirmDraft(d: ChatDraft): Promise<void> {
  if (d.mock) {
    uni.showToast({ title: '演示识别结果不能记入记录', icon: 'none' });
    return;
  }
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
      source: d.recordSource ?? 'ai_text',
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
  /* 底部留白要盖过"悬浮底栏 + 它与 tabBar 的间距"：
     H5 里底栏顶边离底 104+190≈294rpx，App 里 40+190≈230rpx，取 320rpx 两头都够。
     少了这一截，滚到最底时最后一条消息会被底栏压住。 */
  padding: var(--s-4) var(--s-3) calc(320rpx + env(safe-area-inset-bottom));
  background: var(--c-bg);
}

/* 顶部细工具条（2026-09-19 取代原来的双行页头）。
   高度对齐右边那颗 64rpx 的按钮，整条比原页头矮一半；
   左边是当日状态、右边是新对话——首屏把空间还给对话本身。
   ⚠️ 不要在这里再放页面标题：原生导航栏已经有了。 */
.page-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
  min-height: 64rpx;
}
.bar-stat { color: var(--c-text-2); font-size: 23rpx; }
.bar-num { color: var(--c-primary); font-weight: 500; }
/* 头部右上角动作（新对话）：与 manage 页的批量删除按钮同一套 */
.head-btn {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: 64rpx;
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 24rpx;
}

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
/* 来源标签：这个热量是"查到的"还是"估的"必须标出来，别让用户以为是自己的数。
   三档三种颜色（见 sourceTagClass），一眼能分出可信度。 */
.draft-tag {
  margin-left: var(--s-1);
  padding: 2rpx var(--s-1);
  border-radius: var(--r-sm);
  background: var(--c-warn-bg);
  color: var(--c-warn-text);
  font-size: 20rpx;
  font-weight: 400;
}
/* 已核对：和权威数据源精确对上了——最好的情况，用主色 */
.draft-tag.exact { background: var(--c-primary-bg); color: var(--c-primary); }
/* 按主料推算：查到了主料，但按烹饪方式修正过——有依据，但不是精确值 */
.draft-tag.derived { background: var(--c-tint-sage); color: var(--c-sage-text); }

/* ---------- AI 的查询过程 ---------- */
/* 显示"它去查了什么"。刻意做得很轻：这是过程提示，不是内容本身——
   抢了回复的注意力就本末倒置了。 */
.trace {
  margin-top: var(--s-2);
  padding-top: var(--s-2);
  border-top: 2rpx dashed var(--c-border);
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}
.trace-row { display: flex; align-items: center; gap: var(--s-2); }
/* 用一个小圆点表示成功/失败（不用 emoji，也不用图标字体） */
.trace-dot {
  flex: 0 0 auto;
  width: 10rpx;
  height: 10rpx;
  border-radius: 50%;
  background: var(--c-primary-weak);
}
.trace-dot.fail { background: var(--c-warn); }
.trace-text { color: var(--c-text-3); font-size: 22rpx; line-height: 1.5; }
/* "思考中…"气泡里的实时步骤：不用再画分隔线（气泡本身就小），
   紧凑一点，别让它长得像一条完整回复 */
.trace.live { margin-top: var(--s-1); padding-top: 0; border-top: none; }
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
/* ⚠️ bottom 必须**分平台**写（2026-09-19 踩过，与 menu 页 .cart-bar 同一个坑）：
   H5 的 tabBar 是 DOM、盖在页面上（实测 96rpx），bottom 得让过它 → 104rpx；
   App / 小程序的 tabBar 是原生控件、页面区域不含它，bottom 就是真实间距 → 40rpx。
   只写一句 104rpx 的话，手机（App）上会离 tabBar 还有 104rpx，看着"没有变化"。 */
/* #ifdef H5 */
.bottom-bar { bottom: calc(104rpx + env(safe-area-inset-bottom)); }
/* #endif */
/* #ifndef H5 */
.bottom-bar { bottom: calc(40rpx + env(safe-area-inset-bottom)); }
/* #endif */
.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  z-index: 20;
  /* ⚠️ 必须 border-box：left/right:0 + 左右 padding 时，content-box 会让
     实际宽度 = 100% + padding，整条溢出到屏幕外，"发送"按钮就被挤出可视区了。 */
  box-sizing: border-box;
  padding: 0 var(--s-3);
  background: var(--c-bg);
}

.mock-hint {
  margin-bottom: var(--s-1);
  padding: var(--s-1) var(--s-3);
  border-radius: var(--r-sm);
  background: var(--c-muted);
  color: var(--c-text-2);
  font-size: 22rpx;
  line-height: 1.5;
}
/* 「今天已记」那张卡片 2026-09-19 已上移到顶部 .page-bar：
   底部浮层只留输入框，少一层盒子、少 39px 高度 */

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
.composer-photo {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-pill);
  color: var(--c-text-2);
  font-size: 24rpx;
  box-sizing: border-box;
}
.composer-photo.disabled { opacity: 0.55; }
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
