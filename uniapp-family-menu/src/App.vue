<script setup>
import { onLaunch } from '@dcloudio/uni-app';
import { initCloud } from './services/cloud';

onLaunch(() => {
  initCloud();
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
