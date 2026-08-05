<script setup>
import { markRaw } from 'vue';
import WorkspaceTabs from '../components/WorkspaceTabs.vue';
import Overview from './Overview.vue';
import Orders from './Orders.vue';

const tabs = [
  { id: 'overview', label: '跨店总览', component: markRaw(Overview) },
  { id: 'orders', label: '跨店订单', component: markRaw(Orders) },
];
</script>

<template>
  <WorkspaceTabs :tabs="tabs" default-tab="overview" workspace-name="operations" label="经营中心功能" />
</template>
