/**
 * AI 对话接口（对接自己的 FastAPI 后端）。
 *
 * 一轮对话返回三样东西：
 *   · `reply`   —— 给用户看的自然语言回复
 *   · `actions` —— **待用户确认**的动作草案（如"记一笔热量"）
 *   · `steps`   —— 本轮 AI 调用了哪些工具（查冰箱/查菜单/查热量）
 *
 * ⭐ 后端是个会用工具的 Agent（2026-09-21 起）：它能自己去查冰箱、查菜单再回答。
 *    所以界面除了显示回复，还会把 `steps` 亮出来——否则用户会觉得
 *    "它怎么知道我冰箱里有什么"。
 *
 * ⚠️ 这个接口**不写业务数据**。后端只给"提议"，真正的写入发生在用户点确认卡片之后，
 *    由调用方复用 health.ts 的 addCalorieLog 完成。
 *    边界这么切，是为了让 AI 没有直接改数据的能力——它从自然语言里抽错了，
 *    最多是卡片显示错，不会把脏数据写进用户的记录。
 *    （后端的工具清单里也**一个写操作都没有**，这条边界是一致的。）
 *
 * 关于上下文（2026-09-18 起）：
 *    **后端自己从 ai_chat_messages 取最近几条**，前端不再传 history——
 *    传的话就等于让前端负责记忆，刷新/换设备上下文就断了。
 *    「新对话」= 调 clearAiMessages 清空后端历史，上下文从头开始。
 */

import { request } from './http';

/** 待用户确认的动作草案 */
export interface ActionDraft {
  /** 动作类型，目前只有 create_calorie_log */
  kind: string;
  food_name: string;
  /** 用户没说份量就是 null —— 界面据此**不显示重量** */
  portion: string | null;
  /** 千卡；模型估算失败时为 null，此时让用户自己在卡片上填 */
  calories: number | null;
  /** 热量是否为模型估算（用户没给热量时为 true，界面要标出来） */
  calories_estimated: boolean;
  /** 食用日期 yyyy-mm-dd */
  eaten_at: string;
  /**
   * 这个热量是**怎么来的**（可信度分级）。
   *
   * - `mcp_exact`    精确查到权威数据        → 界面标「已核对」
   * - `mcp_derived`  查到主料 + 按做法推算   → 界面标「按主料推算」
   * - `llm_estimate` 纯模型估算              → 界面标「估算」
   *
   * ⚠️ 为什么要有它：以前热量全是模型估的，同一个红烧肉今天 400 明天 520，
   * 用户既看不出这是估的，也无从判断准不准。现在标出来，
   * 至少让人知道"这个数字能不能信"。
   */
  source?: string;
  /** 命中的食材名（如"红烧肉"→"猪肉(肥)"）。让用户知道这个数是"拿什么查的" */
  matched_food?: string | null;
}

/** 一步工具调用（后端返回的过程记录，只给界面展示用） */
export interface AgentStepInfo {
  /** 工具名，如 list_fridge_items / lookup_nutrition */
  tool: string;
  ok: boolean;
  /** 一句话摘要，如「4 条食材」 */
  detail: string;
  /** 传进去的参数，如 { keyword: '白菜' } */
  arguments: Record<string, unknown>;
}

/** 一轮对话的返回 */
export interface AiChatResponse {
  reply: string;
  /** log / chat / recommend */
  intent: string;
  actions: ActionDraft[];
  /** 后端没配 Key 时为 true，界面要明说"演示数据" */
  mock: boolean;
  /**
   * 本轮 AI 调用了哪些工具（按顺序）。
   *
   * ⭐ 为什么要露出来：AI 现在会自己去查冰箱、查菜单，
   * 如果只显示最后那句话，用户会觉得"它怎么知道我冰箱里有什么"。
   * 把过程亮出来才有"它真的去看了"的实感。
   * 空数组也是有信息量的：说明这轮它一次都没查（闲聊）。
   */
  steps?: AgentStepInfo[];
}

/** 一条历史消息（后端返回的原始结构） */
interface AiChatMessageDto {
  id: number;
  role: string;
  content: string;
  created_at: string;
}

/** 历史消息（转成前端驼峰后的样子）。只回文本——
 *  确认卡片上的「已记下」是本地状态，回放卡片会诱导用户重复记录 */
export interface AiChatHistoryMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

/** 发一句话给 AI。
 *
 * @param message 用户这一句
 * @param spaceId 当前家庭组。
 *   ⚠️ 改造后（2026-09-21）这个值**真的会被用上**了：AI 会拿它去查冰箱、查菜单。
 *      改造前只是透传（那时 AI 只会抽字段，不碰家庭数据）。
 *      服务端**不信任**这个值——会再过一次成员校验，不是这家人直接拒绝。
 */
export async function sendAiMessage(message: string, spaceId?: string): Promise<AiChatResponse> {
  const data: Record<string, unknown> = { message };
  if (spaceId) data.space_id = spaceId;
  return await request<AiChatResponse>({ url: '/ai/chat', method: 'POST', data });
}

/** 拉最近的对话历史（时间正序），进页面时回放 */
export async function fetchAiMessages(limit = 50): Promise<AiChatHistoryMessage[]> {
  const rows = await request<AiChatMessageDto[]>({
    url: `/ai/chat/messages?limit=${limit}`,
  });
  return rows.map((row) => ({
    id: row.id,
    // 后端只会有 user / assistant 两种，越界的按 AI 处理（界面渲染更安全）
    role: row.role === 'user' ? 'user' : 'assistant',
    content: row.content,
    createdAt: row.created_at,
  }));
}

/** 清空对话历史（「新对话」）。返回清掉的条数 */
export async function clearAiMessages(): Promise<number> {
  const data = await request<{ cleared: number }>({ url: '/ai/chat/messages', method: 'DELETE' });
  return data.cleared;
}
