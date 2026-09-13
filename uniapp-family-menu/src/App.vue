<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app';
import { initCloud } from './services/cloud';
import { ensureLogin } from './services/auth-api';

onLaunch(() => {
  initCloud();

  // 静默登录：wx.login 不需要用户点授权，用户完全无感知。
  // 启动阶段刻意不弹任何错误提示——后端没启动或网络不通时也要能正常进入应用，
  // 真正用到家庭组功能时，那个页面会给出明确的说明和处理办法。
  ensureLogin().catch(() => undefined);
});
</script>

<style>
page {
  min-height: 100%;
  background: #fff7ed;
  color: #431407;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
</style>
