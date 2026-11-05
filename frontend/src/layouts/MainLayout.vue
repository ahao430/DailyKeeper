<template>
  <el-container class="layout">
    <el-aside width="220px" class="layout-aside">
      <div class="brand">
        <el-icon :size="22" color="#409eff"><Calendar /></el-icon>
        <span class="brand-name">DailyKeeper</span>
      </div>
      <el-menu class="layout-menu" :default-active="activeMenu" router>
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <span>总览</span>
        </el-menu-item>
        <el-menu-item index="/platforms">
          <el-icon><Platform /></el-icon>
          <span>平台管理</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><AlarmClock /></el-icon>
          <span>任务中心</span>
        </el-menu-item>
        <el-menu-item index="/executions">
          <el-icon><Document /></el-icon>
          <span>执行日志</span>
        </el-menu-item>
        <el-menu-item index="/resources">
          <el-icon><DataAnalysis /></el-icon>
          <span>资源看板</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="layout-body">
      <el-header class="layout-header" height="56px">
        <div class="header-title">DailyKeeper 每日管家</div>
        <div class="header-right">
          <span v-if="username" class="header-user">{{ username }}</span>
          <el-button text type="danger" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AlarmClock,
  Calendar,
  DataAnalysis,
  Document,
  Odometer,
  Platform,
  Setting,
} from "@element-plus/icons-vue";
import { getMe } from "../api";
import { useAuth } from "../composables/auth";

const route = useRoute();
const router = useRouter();
const { username, clearToken } = useAuth();

const activeMenu = computed(() => route.path);

onMounted(async () => {
  if (!username.value) {
    try {
      const me = await getMe();
      username.value = me.username;
    } catch {
      // 拉取失败不阻塞布局（401 时拦截器会跳回登录页）
    }
  }
});

function handleLogout(): void {
  clearToken();
  router.push("/login");
}
</script>

<style scoped>
.layout {
  height: 100vh;
}

.layout-aside {
  display: flex;
  flex-direction: column;
  background-color: #fff;
  border-right: 1px solid var(--el-border-color-light);
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 56px;
  padding: 0 20px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.brand-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.layout-menu {
  flex: 1;
  border-right: none;
}

.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-user {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.layout-main {
  background-color: var(--el-fill-color-lighter);
  overflow-y: auto;
}
</style>
