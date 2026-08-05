<script setup>
import { markRaw } from 'vue';
import WorkspaceTabs from '../components/WorkspaceTabs.vue';
import Shops from './Shops.vue';
import Reports from './Reports.vue';
import Backups from './Backups.vue';

const tabs = [
  { id: 'shops', label: '店铺列表', component: markRaw(Shops) },
  { id: 'reports', label: '经营报表', component: markRaw(Reports) },
  { id: 'backups', label: '数据备份', component: markRaw(Backups) },
];
</script>

<template>
  <WorkspaceTabs :tabs="tabs" default-tab="shops" workspace-name="shops" label="店铺管理功能" />
</template>
