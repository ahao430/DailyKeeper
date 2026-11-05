<template>
  <div class="dashboard-page">
    <div class="page-header">
      <h2 class="page-title">总览</h2>
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <el-row :gutter="16">
      <el-col v-for="card in statCards" :key="card.label" :xs="12" :sm="12" :md="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" :style="{ color: card.color, backgroundColor: card.bg }">
            <el-icon :size="26"><component :is="card.icon" /></el-icon>
          </div>
          <div class="stat-body">
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="info-card">
      <template #header>
        <span class="info-title">系统信息</span>
      </template>
      <el-descriptions v-if="info" :column="2" border>
        <el-descriptions-item label="应用名称">{{ info.app_name }}</el-descriptions-item>
        <el-descriptions-item label="版本">v{{ info.version }}</el-descriptions-item>
        <el-descriptions-item label="运行环境">{{ info.env }}</el-descriptions-item>
        <el-descriptions-item label="数据库">{{ info.database }}</el-descriptions-item>
        <el-descriptions-item label="服务器时区">{{ info.timezone }}</el-descriptions-item>
        <el-descriptions-item label="已加载插件">{{ info.plugins }} 个</el-descriptions-item>
        <el-descriptions-item label="调度心跳">
          <template v-if="heartbeat">
            <span class="heartbeat-at">{{ heartbeat.at }}</span>
            <el-tag
              :type="heartbeat.fresh ? 'success' : 'danger'"
              size="small"
              class="heartbeat-tag"
            >
              {{ heartbeat.fresh ? "心跳正常" : "心跳异常" }}
            </el-tag>
          </template>
          <el-tag v-else type="info" size="small">未上报</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="通知开关">
          <el-tag :type="info.notifications_enabled ? 'success' : 'info'" size="small">
            {{ info.notifications_enabled ? "已启用" : "已关闭" }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-empty v-else-if="!loading" description="暂无系统信息" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue";
import {
  AlarmClock,
  CircleCheck,
  Odometer,
  Refresh,
  WarningFilled,
} from "@element-plus/icons-vue";
import dayjs from "dayjs";
import { getSystemInfo } from "../api";
import { extractErrorMessage } from "../api/client";
import type { SystemInfo } from "../api/types";
import { ElMessage } from "element-plus";

interface StatCard {
  label: string;
  value: number;
  icon: Component;
  color: string;
  bg: string;
}

const loading = ref(false);
const info = ref<SystemInfo | null>(null);

const heartbeat = computed(() => {
  if (!info.value?.scheduler_heartbeat) {
    return null;
  }
  const raw = info.value.scheduler_heartbeat.at;
  return { ...info.value.scheduler_heartbeat, at: formatTime(raw) };
});

const statCards = computed<StatCard[]>(() => {
  const today = info.value?.executions_today ?? 0;
  const success = info.value?.executions_today_success ?? 0;
  return [
    {
      label: "平台账号",
      value: info.value?.accounts ?? 0,
      icon: Odometer,
      color: "#409eff",
      bg: "#ecf5ff",
    },
    {
      label: "今日任务",
      value: today,
      icon: AlarmClock,
      color: "#e6a23c",
      bg: "#fdf6ec",
    },
    {
      label: "今日成功",
      value: success,
      icon: CircleCheck,
      color: "#67c23a",
      bg: "#f0f9eb",
    },
    {
      label: "待处理异常",
      value: Math.max(today - success, 0),
      icon: WarningFilled,
      color: "#f56c6c",
      bg: "#fef0f0",
    },
  ];
});

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm:ss") : value;
}

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    info.value = await getSystemInfo();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载系统信息失败"));
  } finally {
    loading.value = false;
  }
}

onMounted(loadAll);
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  color: var(--el-text-color-primary);
}

.stat-card {
  margin-bottom: 16px;
}

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 10px;
  flex-shrink: 0;
}

.stat-value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--el-text-color-primary);
}

.stat-label {
  margin-top: 2px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.info-card {
  margin-top: 8px;
}

.info-title {
  font-weight: 600;
}

.heartbeat-at {
  margin-right: 8px;
}

.heartbeat-tag {
  vertical-align: middle;
}
</style>
