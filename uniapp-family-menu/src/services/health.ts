/**
 * 个人健康档案 + 热量记录 + 拍照识别。
 *
 * 身份完全由后端从令牌解析——前端既不传、也传不了 user_id。
 * 这和 services/user.ts 的约定一致：只要能传 ID，别人就能传别人的 ID 读到别人的数据。
 */

import { ApiError, BASE_URL, request } from './http';
import { clearToken, getToken } from '../utils/token';

export type Gender = 'male' | 'female' | 'other';
export type Goal = 'lose' | 'maintain' | 'gain';

/** 后端返回的健康档案 */
export interface HealthProfile {
  id: number;
  user_id: number;
  gender: Gender | null;
  height_cm: number | null;
  weight_kg: number | null;
  goal: Goal | null;
  diet_preferences: string | null;
  updated_at: string;
}

/** 一条热量记录 */
export interface CalorieLog {
  id: number;
  /** 食用日期 yyyy-mm-dd */
  eaten_at: string;
  food_name: string;
  calories: number;
  portion: string | null;
  /** 识别用图相对路径，显示时过 resolveFileUrl */
  image_url: string | null;
  /** 来源：vision 拍照识别 / manual 手动添加 */
  source: string;
  created_at: string;
}

/**
 * 单条识别结果。
 *
 * ⚠️ `calories` 是后端用 `kcal_per_100g × grams / 100` 算出来的，不是模型报的整份值。
 * 拆开的意义在于前端能按份量缩放：照片里估份量本来就模糊（实测这是误差的主要来源），
 * 所以让用户选 小份/中份/大份 比让模型猜可靠。
 */
export interface FoodEstimate {
  food_name: string;
  calories: number;
  portion: string | null;
  confidence: number | null;
  /** 这一份的估计克重，前端当「中份」基准用；为 null 时就不给份量选择 */
  grams: number | null;
  /** 每 100 克多少千卡；为 null 时说明后端没查到密度，热量会显示 0 */
  kcal_per_100g: number | null;
}

/** 拍照识别的返回 */
export interface RecognizeFoodResponse {
  items: FoodEstimate[];
  /** 是否占位数据（没配识别 Key 时为 true，前端提示"演示数据"） */
  mock: boolean;
}

/** 修改健康档案的请求体：所有字段可选 */
export interface HealthProfileUpdate {
  gender?: Gender | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  goal?: Goal | null;
  diet_preferences?: string | null;
}

/** 新增热量记录的请求体 */
export interface CalorieLogCreate {
  /** 食用日期，默认今天 */
  eaten_at?: string;
  food_name: string;
  calories: number;
  portion?: string | null;
  image_url?: string | null;
  source?: string;
}

const API = '/users/me';

/** 读取健康档案，还没有时返回 null */
export async function fetchHealthProfile(): Promise<HealthProfile | null> {
  return await request<HealthProfile | null>({ url: `${API}/health-profile` });
}

/**
 * 修改健康档案。
 *
 * 后端用 PATCH 语义（部分更新），这里走 POST 兼容小程序（和 updateCurrentUser 同理）。
 * 没传的字段不会动，传 null 表示清空。
 */
export async function updateHealthProfile(payload: HealthProfileUpdate): Promise<HealthProfile> {
  const data: Record<string, unknown> = {};
  if (payload.gender !== undefined) data.gender = payload.gender;
  if (payload.height_cm !== undefined) data.height_cm = payload.height_cm;
  if (payload.weight_kg !== undefined) data.weight_kg = payload.weight_kg;
  if (payload.goal !== undefined) data.goal = payload.goal;
  if (payload.diet_preferences !== undefined) data.diet_preferences = payload.diet_preferences;
  return await request<HealthProfile>({ url: `${API}/health-profile`, method: 'POST', data });
}

/** 热量记录列表，可按日期区间（yyyy-mm-dd）过滤 */
export async function fetchCalorieLogs(params?: { date_from?: string; date_to?: string }): Promise<CalorieLog[]> {
  let query = '';
  if (params && (params.date_from || params.date_to)) {
    const sp = new URLSearchParams();
    if (params.date_from) sp.set('date_from', params.date_from);
    if (params.date_to) sp.set('date_to', params.date_to);
    query = `?${sp.toString()}`;
  }
  return await request<CalorieLog[]>({ url: `${API}/calorie-logs${query}` });
}

/** 新增一条热量记录 */
export async function addCalorieLog(payload: CalorieLogCreate): Promise<CalorieLog> {
  const data: Record<string, unknown> = {};
  if (payload.eaten_at !== undefined) data.eaten_at = payload.eaten_at;
  data.food_name = payload.food_name;
  data.calories = payload.calories;
  if (payload.portion !== undefined) data.portion = payload.portion;
  if (payload.image_url !== undefined) data.image_url = payload.image_url;
  if (payload.source !== undefined) data.source = payload.source;
  return await request<CalorieLog>({ url: `${API}/calorie-logs`, method: 'POST', data });
}

/** 修改热量记录的请求体。
 *
 *  整条替换（四个字段都必填，`portion` 传 null = 清掉份量），不做部分更新——
 *  部分更新时"portion 传 null"到底是"清掉"还是"没传"，前后端都分不清。
 *  编辑弹层手上永远有完整的一条，所以整条送回去最省事也最不含糊。 */
export interface CalorieLogUpdate {
  eaten_at: string;
  food_name: string;
  calories: number;
  portion: string | null;
}

/** 修改一条热量记录 */
export async function updateCalorieLog(id: number, payload: CalorieLogUpdate): Promise<CalorieLog> {
  return await request<CalorieLog>({
    url: `${API}/calorie-logs/${id}`,
    method: 'PUT', // 用 PUT 不用 PATCH：小程序的合法 method 里没有 PATCH（见 http.ts 的注释）
    data: { ...payload },
  });
}

/** 删除一条热量记录 */
export async function deleteCalorieLog(id: number): Promise<void> {
  await request<void>({ url: `${API}/calorie-logs/${id}`, method: 'DELETE' });
}

/**
 * 拍照识别食物热量。
 * @param filePath uni.chooseImage 返回的本地临时图片路径；服务端只临时识别，不永久保存。
 */
export async function recognizeFoodImage(filePath: string): Promise<RecognizeFoodResponse> {
  return await new Promise<RecognizeFoodResponse>((resolve, reject) => {
    const token = getToken();
    uni.uploadFile({
      url: `${BASE_URL}/vision/recognize-food/image`,
      filePath,
      name: 'file',
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        try {
          const body = JSON.parse(res.data) as { code?: number; message?: string; data?: RecognizeFoodResponse };
          if (res.statusCode === 401) {
            clearToken();
            reject(new ApiError(body.message || '登录已过期，请重新登录', body.code ?? 1001, 401));
            return;
          }
          if (!body || typeof body.code !== 'number') {
            reject(new ApiError('服务端返回格式异常', -1, res.statusCode));
            return;
          }
          if (body.code !== 0 || !body.data) {
            reject(new ApiError(body.message || '识别失败', body.code, res.statusCode));
            return;
          }
          resolve(body.data);
        } catch {
          reject(new ApiError('服务端返回格式异常', -1, res.statusCode));
        }
      },
      fail: () => reject(new ApiError('无法连接到服务器，请确认后端已启动', -2, 0)),
    });
  });
}
