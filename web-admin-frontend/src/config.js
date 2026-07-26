// ============================================================
// 唯一需要你手动填写的地方：web-admin 云函数的 HTTP 访问服务地址
// ------------------------------------------------------------
// 在云开发控制台 → 当前环境 → HTTP 访问服务，新增一条指向 web-admin
// 云函数的路径（例如 /web-admin），把分配到的完整公网地址粘到下面。
// 形如：https://你的环境.service.tcloudbase.com/web-admin
// ============================================================
export const API_BASE = 'https://cloud1-d2gua37h7753f3812-1454825551.ap-shanghai.app.tcloudbase.com/web-admin';

// 登录会话在浏览器里保存的键名（localStorage）
export const TOKEN_KEY = 'web_admin_token';
export const USERNAME_KEY = 'web_admin_username';
