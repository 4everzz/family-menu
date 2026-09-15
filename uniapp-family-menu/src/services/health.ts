/**
 * 个人健康档案 + 热量记录 + 拍照识别。
 *
 * 身份完全由后端从令牌解析——前端既不传、也传不了 user_id。
 * 这和 services/user.ts 的约定一致：只要能传 ID，别人就能传别人的 ID 读到别人的数据。
 */

import { request } from './http';

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

/** 单条识别结果 */
export interface FoodEstimate {
  food_name: string;
  calories: number;
  portion: string | null;
  confidence: number | null;
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

/** 删除一条热量记录 */
export async function deleteCalorieLog(id: number): Promise<void> {
  await request<void>({ url: `${API}/calorie-logs/${id}`, method: 'DELETE' });
}

/**
 * 拍照识别食物热量。
 * @param imageUrl 上传接口返回的相对路径（/uploads/...）
 */
export async function recognizeFood(imageUrl: string): Promise<RecognizeFoodResponse> {
  return await request<RecognizeFoodResponse>({
    url: '/vision/recognize-food',
    method: 'POST',
    data: { image_url: imageUrl },
  });
}
