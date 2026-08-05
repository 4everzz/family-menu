<script setup>
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const props = defineProps({
  tabs: { type: Array, required: true },
  defaultTab: { type: String, required: true },
  label: { type: String, required: true },
  workspaceName: { type: String, required: true },
});

const route = useRoute();
const router = useRouter();

const activeTab = computed(() => props.tabs.find((tab) => tab.id === route.query.tab)
  || props.tabs.find((tab) => tab.id === props.defaultTab)
  || props.tabs[0]);

watch(
  () => [route.name, route.query.tab],
  ([routeName, tab]) => {
    // 被 keep-alive 缓存的其他工作区不能改动当前路由，否则会互相触发跳转循环。
    if (routeName !== props.workspaceName) return;
    if (props.tabs.some((item) => item.id === tab)) return;
    router.replace({ name: route.name, query: { ...route.query, tab: props.defaultTab } });
  },
  { immediate: true },
);

function selectTab(id) {
  if (route.name !== props.workspaceName) return;
  if (id === activeTab.value.id) return;
  router.replace({ name: route.name, query: { ...route.query, tab: id } });
}
</script>

<template>
  <section class="workspace">
    <div class="workspace-tabs" role="tablist" :aria-label="label">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="workspace-tab"
        :class="{ active: activeTab.id === tab.id }"
        type="button"
        role="tab"
        :aria-selected="activeTab.id === tab.id"
        @click="selectTab(tab.id)"
      >
        {{ tab.label }}
      </button>
    </div>

    <keep-alive>
      <component :is="activeTab.component" />
    </keep-alive>
  </section>
</template>

<style scoped>
.workspace { min-width: 0; }
.workspace-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  width: fit-content;
  max-width: 100%;
  margin: 0 0 22px;
  padding: 4px;
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.workspace-tab {
  min-width: max-content;
  height: 34px;
  margin: 0;
  padding: 0 13px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--ink-soft);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 34px;
  cursor: pointer;
}
.workspace-tab:hover { background: var(--surface-2); }
.workspace-tab.active { background: var(--accent-soft); color: var(--accent-ink); }
.workspace-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
@media (max-width: 720px) {
  .workspace-tabs { width: 100%; }
}
</style>
