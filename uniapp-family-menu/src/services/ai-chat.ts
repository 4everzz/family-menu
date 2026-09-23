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

import { ApiError, BASE_URL, request } from './http';
import { getToken } from '../utils/token';

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

/* ==================== 流式（SSE）版本 ====================
 *
 * 一轮 Agent 最多 4 次串行模型调用，前后 10 秒起步，用户全程只看到"思考中…"。
 * 流式通道把"查冰箱 → 查到了"这类步骤**在发生时**推给界面，
 * 等待从黑盒变成看得见的进度。最终结果仍是一次性给整包，
 * 所以确认卡片、落库、回放的逻辑与非流式完全一致。
 */

/** 增量 UTF-8 解码器。
 *
 * 为什么不直接用 TextDecoder：
 *   ① App 端的 JS 引擎里**没有** TextDecoder，而 onChunkReceived 给的是 ArrayBuffer；
 *   ② 一个汉字（3 字节）可能被切在两块 chunk 的交界处，
 *      不完整的尾部必须留到下一块一起解，否则会解出乱码。
 * 有 TextDecoder 的环境（H5）直接用它的 stream 模式，行为等价。
 */
type TextDecoderLike = { decode(input: Uint8Array, options?: { stream?: boolean }): string };

class Utf8StreamDecoder {
  /** 上一块结尾没解完的半截多字节字符 */
  private pending: number[] = [];
  private td: TextDecoderLike | null;

  constructor() {
    // 不直接引用 TextDecoder 类型名：App 编译目标的 TS lib 里未必有它
    const ctor = (globalThis as Record<string, unknown>).TextDecoder as
      | (new (label: string) => TextDecoderLike)
      | undefined;
    this.td = ctor ? new ctor('utf-8') : null;
  }

  decode(chunk: string | ArrayBuffer): string {
    if (typeof chunk === 'string') return chunk;
    const bytes = new Uint8Array(chunk);
    if (this.td) return this.td.decode(bytes, { stream: true });

    // 手写增量 UTF-8 解码（App 端路径）
    const all = this.pending.length ? [...this.pending, ...bytes] : [...bytes];
    this.pending = [];
    let out = '';
    let i = 0;
    while (i < all.length) {
      const b = all[i];
      let need: number; // 还差几个续字节
      let cp: number;
      if (b < 0x80) { need = 0; cp = b; }
      else if ((b & 0xe0) === 0xc0) { need = 1; cp = b & 0x1f; }
      else if ((b & 0xf0) === 0xe0) { need = 2; cp = b & 0x0f; }
      else if ((b & 0xf8) === 0xf0) { need = 3; cp = b & 0x07; }
      else { out += '\uFFFD'; i += 1; continue; } // 孤立的续字节：替换符，跳过
      if (i + need >= all.length) {
        this.pending = all.slice(i); // 尾巴是半截字符，等下一块
        break;
      }
      let ok = true;
      for (let k = 1; k <= need; k += 1) {
        const cont = all[i + k];
        if ((cont & 0xc0) !== 0x80) { ok = false; break; }
        cp = (cp << 6) | (cont & 0x3f);
      }
      if (!ok) { out += '\uFFFD'; i += 1; continue; }
      i += need + 1;
      if (cp > 0xffff) {
        // > U+FFFF 要拆成代理对（JS 字符串是 UTF-16）
        const v = cp - 0x10000;
        out += String.fromCharCode(0xd800 + (v >> 10), 0xdc00 + (v & 0x3ff));
      } else {
        out += String.fromCharCode(cp);
      }
    }
    return out;
  }
}

/** 从缓冲里按空行切出**完整的** SSE 帧；最后一段可能不完整，留在缓冲里等下一块。 */
function extractSseFrames(
  buffer: string,
): { frames: { event: string; data: string }[]; rest: string } {
  const frames: { event: string; data: string }[] = [];
  let rest = buffer;
  for (;;) {
    const idx = rest.indexOf('\n\n');
    if (idx === -1) break;
    const block = rest.slice(0, idx);
    rest = rest.slice(idx + 2);
    let event = 'message';
    const dataLines: string[] = [];
    for (const rawLine of block.split('\n')) {
      const line = rawLine.trim();
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    frames.push({ event, data: dataLines.join('\n') });
  }
  return { frames, rest };
}

/** 发起一条流式请求（不做任何回落——那是 sendAiMessageStream 的事）。 */
function streamAiChat(
  message: string,
  spaceId: string | undefined,
  onStep: (step: AgentStepInfo) => void,
): Promise<AiChatResponse> {
  const body: Record<string, unknown> = { message };
  if (spaceId) body.space_id = spaceId;

  return new Promise<AiChatResponse>((resolve, reject) => {
    const header: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token) header.Authorization = `Bearer ${token}`;

    const decoder = new Utf8StreamDecoder();
    let buffer = '';
    let settled = false;

    const fail = (err: ApiError): void => {
      if (settled) return;
      settled = true;
      reject(err);
    };

    const handleFrame = (event: string, data: string): void => {
      if (event === 'step') {
        try {
          onStep(JSON.parse(data) as AgentStepInfo);
        } catch {
          // 单帧坏了就丢掉这一帧，不能让一次解析失败炸掉整轮对话
        }
        return;
      }
      if (event === 'error') {
        // 后端明确拒绝（额度用完、参数不对等）。原样抛给上层——
        // ⚠️ 这种错误绝不能触发"回落重试"，重试等于再扣一次额度
        try {
          const err = JSON.parse(data) as { code?: number; message?: string };
          fail(new ApiError(err.message || 'AI 处理失败', err.code ?? -1));
        } catch {
          fail(new ApiError('AI 处理失败', -1));
        }
        return;
      }
      if (event === 'message') {
        try {
          const resp = JSON.parse(data) as AiChatResponse;
          settled = true;
          resolve(resp);
        } catch {
          fail(new ApiError('服务端返回格式异常', -1));
        }
      }
      // start / done：对调用方没有意义，不处理
    };

    const options = {
      url: `${BASE_URL}/ai/chat/stream`,
      method: 'POST',
      data: body,
      header,
      // ⭐ 开启 chunked 收流。较新基础库里 App / H5 / 小程序都支持；
      //    老平台忽略这个标志 → 走下面 success 里的"整包兜底"，行为照样正确
      enableChunked: true,
      success: (res: { statusCode: number; data: unknown }) => {
        // 兜底：onChunkReceived 一次都没触发（平台不支持 chunked）
        // → 把整个响应体当完整 SSE 解析一遍
        if (!settled && typeof res.data === 'string') {
          const whole = extractSseFrames(buffer + res.data);
          for (const f of whole.frames) handleFrame(f.event, f.data);
        }
        if (!settled) fail(new ApiError('服务端返回格式异常', -1, res.statusCode));
      },
      fail: () => fail(new ApiError('无法连接到服务器，请确认后端已启动', -2, 0)),
    };

    const task = uni.request(options as unknown as Parameters<typeof uni.request>[0]);
    const chunkTask = task as unknown as {
      onChunkReceived?: (cb: (res: { data: string | ArrayBuffer }) => void) => void;
    };
    chunkTask.onChunkReceived?.((res) => {
      if (settled) return;
      buffer += decoder.decode(res.data ?? '');
      const parsed = extractSseFrames(buffer);
      buffer = parsed.rest;
      for (const f of parsed.frames) handleFrame(f.event, f.data);
    });
  });
}

/**
 * 流式发一句话：工具步骤通过 `onStep` **实时**回调（"查冰箱 · 4 条食材"当场出现），
 * 最终 resolve 整包结果（结构和 {@link sendAiMessage} 完全一致）。
 *
 * ⭐ 兜底策略（流式是新链路，不能让它变成单点故障）：
 *   · 连不上 / 后端还没有流式端点（HTTP ≥ 400）→ 自动回落到一次性接口，
 *     行为与从前完全一致；
 *   · 后端明确拒绝（额度用完等，走 `event: error`）→ 原样抛出，**不重试**。
 */
export async function sendAiMessageStream(
  message: string,
  spaceId: string | undefined,
  onStep: (step: AgentStepInfo) => void,
): Promise<AiChatResponse> {
  try {
    return await streamAiChat(message, spaceId, onStep);
  } catch (error) {
    const transport = error instanceof ApiError && (error.code === -2 || error.httpStatus >= 400);
    if (!transport) throw error;
    return await sendAiMessage(message, spaceId);
  }
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
