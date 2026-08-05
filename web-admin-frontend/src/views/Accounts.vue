<script setup>
import { markRaw } from 'vue';
import WorkspaceTabs from '../components/WorkspaceTabs.vue';
import Users from './Users.vue';
import Members from './Members.vue';
import NicknameRestrictions from './NicknameRestrictions.vue';

const tabs = [
  { id: 'users', label: '用户管理', component: markRaw(Users) },
  { id: 'members', label: '管理员授权', component: markRaw(Members) },
  { id: 'restrictions', label: '昵称限制词', component: markRaw(NicknameRestrictions) },
];
</script>

<template>
  <WorkspaceTabs :tabs="tabs" default-tab="users" workspace-name="accounts" label="账号与权限功能" />
</template>
