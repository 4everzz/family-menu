/**
 * 家庭提醒接口（对接自己的 FastAPI 后端）。
 *
 * 提醒是"派生数据"——后端不单独建表，而是每次从冰箱现有字段（保质期 / 库存）
 * 实时算出来。前端只负责展示，没有任何"已读 / 忽略"状态需要本地维护：
 *   冰箱状态变了，提醒自然就变了，不需要我们额外去记"这一条我点过了"。
 *
 * 这一层和 services/fridge.ts 是同一套写法：
 *   1. 发请求交给 services/http.ts 统一处理（拼地址、带令牌、解析 { code, message, data }）；
 *   2. 把后端下划线字段（related_id）转成前端驼峰（relatedId），转换只在这一个文件做。
 *
 * 关于范围：目前有三类——
 *   · fridge_expiring：临期（warning）/ 已过期（danger），阈值 3 天，后端定；
 *   · fridge_out：库存 <= 0 缺货（danger）；
 *   · order_empty_today：今天这个家还没点单（info，仅提示）。后端从上午 9 点起才产出，
 *     且 `action` 为空字符串表示"不可点击"。
 */

import { request } from './http';

/** 后端返回的提醒结构（原始字段，下划线风格） */
interface AlertDto {
  /** 稳定 ID，形如 "fridge_expiring:123"，前端不用来查库，仅作列表 key */
  id: string;
  /** 提醒类型：fridge_expiring / fridge_out / order_empty_today */
  type: string;
  /** 严重级别：danger（过期/缺货）> warning（临期）> info（仅提示） */
  level: string;
  /** 主标题，如「鸡蛋 已过期」「鸡蛋 2 天后过期」「鸡蛋 缺货」「今天还没有人点单」 */
  title: string;
  /** 补充说明，如「保质期 2026-09-18」「库存 0个」 */
  detail: string;
  /** 关联食材 ID，点了跳去编辑那条食材；order_empty_today 为 null */
  related_id: number | null;
  /** 点击后要去的页面路径；空字符串表示这条不可点击 */
  action: string;
}

/** 提醒（前端使用，驼峰风格） */
export interface Alert {
  id: string;
  type: string;
  /** 严重级别，只可能是 danger / warning / info */
  level: 'danger' | 'warning' | 'info';
  title: string;
  detail: string;
  relatedId: number | null;
  /** 空字符串表示这条只是信息、不可点击 */
  action: string;
}

/** 列表接口返回结构 */
interface AlertListDto {
  items: AlertDto[];
}

/** 把后端字段转成前端结构 */
function toAlert(dto: AlertDto): Alert {
  return {
    id: dto.id,
    type: dto.type,
    // 逐档显式映射，不用 `level === 'danger' ? 'danger' : 'warning'` 那种写法——
    // 那样任何新级别都会被静默压成 warning，改后端加一档前端不会有任何提示。
    level: dto.level === 'danger' ? 'danger' : dto.level === 'info' ? 'info' : 'warning',
    title: dto.title,
    detail: dto.detail || '',
    relatedId: dto.related_id ?? null,
    action: dto.action,
  };
}

/**
 * 拉取某个家庭组的提醒列表。
 *
 * 提醒对家庭成员全员可见（都是全家要处理的事），后端按"是不是这个家成员"放行；
 * 具体哪些食材属于这个家，后端用 space_id 自己筛，前端只传 spaceId。
 */
export async function fetchAlerts(spaceId: string): Promise<Alert[]> {
  const dto = await request<AlertListDto>({ url: `/spaces/${spaceId}/alerts` });
  return (Array.isArray(dto?.items) ? dto.items : []).map(toAlert);
}
