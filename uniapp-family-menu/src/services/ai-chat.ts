/**
 * AI 对话接口（对接自己的 FastAPI 后端）。
 *
 * 一轮对话返回两样东西：
 *   · `reply`   —— 给用户看的自然语言回复
 *   · `actions` —— **待用户确认**的动作草案（如"记一笔热量"）
 *
 * ⚠️ 这个接口**不写库**。后端只给"提议"，真正的写入发生在用户点确认卡片之后，
 *    由调用方复用 health.ts 的 addCalorieLog 完成。
 *    边界这么切，是为了让 AI 没有直接改数据的能力——它从自然语言里抽错了，
 *    最多是卡片显示错，不会把脏数据写进用户的记录。
 *
 * 历史消息本轮只存在页面内存里（关掉页面就没了），每次请求回填最近几轮：
 * 没有历史就不叫对话——"再加一碗"这种省略句全靠它才能理解。
 */

import { request } from './http';

/** 一轮历史消息 */
export interface AiChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

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
}

/** 一轮对话的返回 */
export interface AiChatResponse {
  reply: string;
  /** log / chat / recommend */
  intent: string;
  actions: ActionDraft[];
  /** 后端没配 Key 时为 true，界面要明说"演示数据" */
  mock: boolean;
}

/** 发一句话给 AI。
 *
 * @param message 用户这一句
 * @param history 最近几轮（越旧越靠前），用来理解省略句
 * @param spaceId 当前家庭组；本轮后端只透传不使用，为以后的菜单推荐预留
 */
export async function sendAiMessage(
  message: string,
  history: AiChatTurn[] = [],
  spaceId?: string,
): Promise<AiChatResponse> {
  const data: Record<string, unknown> = { message, history };
  if (spaceId) data.space_id = spaceId;
  return await request<AiChatResponse>({ url: '/ai/chat', method: 'POST', data });
}
