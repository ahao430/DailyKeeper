<template>
  <div class="executions-page">
    <div class="page-header">
      <h2 class="page-title">执行日志</h2>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-select
        v-model="filters.status"
        clearable
        placeholder="状态"
        style="width: 160px"
      >
        <el-option v-for="status in STATUS_OPTIONS" :key="status.value" :label="status.label" :value="status.value" />
      </el-select>
      <el-select
        v-model="filters.accountId"
        clearable
        filterable
        placeholder="账号"
        style="width: 200px"
      >
        <el-option v-for="account in accounts" :key="account.id" :label="accountLabel(account)" :value="account.id" />
      </el-select>
      <el-input
        v-model="filters.taskName"
        clearable
        placeholder="任务名称"
        style="width: 200px"
        @keyup.enter="applyFilters"
      />
      <el-button type="primary" :icon="Search" @click="applyFilters">查询</el-button>
      <el-button :icon="RefreshLeft" @click="resetFilters">重置</el-button>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="executions" row-key="id">
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="account_name" label="账号" min-width="140" show-overflow-tooltip />
        <el-table-column prop="task_name" label="任务" min-width="150" show-overflow-tooltip />
        <el-table-column label="执行线" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="laneTagType(row)" size="small">{{ laneLabel(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="business_date" label="业务日期" width="110" align="center" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="retries" label="重试" width="70" align="center" />
        <el-table-column label="开始时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无执行记录" :image-size="90" />
        </template>
      </el-table>
      <div v-if="hasMore" class="load-more">
        <el-button :loading="loadingMore" @click="loadMore">加载更多</el-button>
      </div>
    </el-card>

    <!-- 执行详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="执行详情" size="520px">
      <div v-if="detail" class="detail-body">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="执行 ID">#{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="账号">{{ detail.account_name }}</el-descriptions-item>
          <el-descriptions-item label="平台实例">{{ detail.instance_name }}</el-descriptions-item>
          <el-descriptions-item label="任务">{{ detail.task_name }}</el-descriptions-item>
          <el-descriptions-item label="业务日期">{{ detail.business_date }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">{{ statusLabel(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatTime(detail.finished_at) }}</el-descriptions-item>
        </el-descriptions>

        <template v-if="detail.result">
          <div class="detail-section-title">执行结果</div>
          <el-alert
            :type="detail.result.success ? 'success' : 'error'"
            show-icon
            :closable="false"
            :title="detail.result.message || (detail.result.success ? '执行成功' : '执行失败')"
          />
          <div class="detail-section-title">返回数据</div>
          <pre class="detail-json">{{ prettyJson(detail.result.data) }}</pre>
          <div class="detail-section-title">指标</div>
          <pre class="detail-json">{{ prettyJson(detail.result.metrics) }}</pre>
        </template>
        <el-alert
          v-else
          type="info"
          show-icon
          :closable="false"
          title="执行尚未产出结果（等待调度或执行中）"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, RefreshLeft, Search } from "@element-plus/icons-vue";
import dayjs from "dayjs";
import { listAccounts, listExecutions } from "../api";
import { extractErrorMessage } from "../api/client";
import type { Execution } from "../api/types";
import { STATUS_LABELS, statusLabel, statusTagType, type TagType } from "../constants/labels";

const PAGE_SIZE = 20;

const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }));

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const loading = ref(false);
const loadingMore = ref(false);
const executions = ref<Execution[]>([]);
const accounts = ref<{ id: number; name: string; display_name: string }[]>([]);
const hasMore = ref(false);
const offset = ref(0);

const filters = reactive({
  status: "",
  accountId: undefined as number | undefined,
  taskName: "",
});

// 点击「查询」后真正生效的过滤条件
const applied = reactive({
  status: "",
  accountId: undefined as number | undefined,
  taskName: "",
});

function accountLabel(account: { name: string; display_name: string }): string {
  return account.display_name ? `${account.name}（${account.display_name}）` : account.name;
}

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm:ss") : value;
}

/** 执行线：Agent / 浏览器 / HTTP（按任务声明的执行通道）。 */
function laneLabel(row: Execution): string {
  if (row.needs_agent) {
    return "Agent";
  }
  if (row.needs_browser) {
    return "浏览器";
  }
  return "HTTP";
}

function laneTagType(row: Execution): TagType {
  if (row.needs_agent) {
    return "warning";
  }
  if (row.needs_browser) {
    return "primary";
  }
  return "info";
}

async function fetchExecutions(reset: boolean): Promise<void> {
  if (reset) {
    loading.value = true;
  } else {
    loadingMore.value = true;
  }
  try {
    const nextOffset = reset ? 0 : offset.value;
    const page = await listExecutions({
      status: applied.status || undefined,
      account_id: applied.accountId ?? undefined,
      task_name: applied.taskName || undefined,
      limit: PAGE_SIZE,
      offset: nextOffset,
    });
    executions.value = reset ? page : [...executions.value, ...page];
    offset.value = nextOffset + page.length;
    hasMore.value = page.length === PAGE_SIZE;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载执行记录失败"));
  } finally {
    loading.value = false;
    loadingMore.value = false;
  }
}

function applyFilters(): void {
  applied.status = filters.status;
  applied.accountId = filters.accountId;
  applied.taskName = filters.taskName.trim();
  void fetchExecutions(true);
}

function resetFilters(): void {
  filters.status = "";
  filters.accountId = undefined;
  filters.taskName = "";
  applied.status = "";
  applied.accountId = undefined;
  applied.taskName = "";
  void fetchExecutions(true);
}

function refresh(): void {
  void fetchExecutions(true);
}

function loadMore(): void {
  void fetchExecutions(false);
}

// ---------------------------------------------------------------------------
// Detail drawer
// ---------------------------------------------------------------------------

const drawerVisible = ref(false);
const detail = ref<Execution | null>(null);

function openDetail(row: Execution): void {
  detail.value = row;
  drawerVisible.value = true;
}

function prettyJson(value: unknown): string {
  if (value === undefined || value === null) {
    return "（无）";
  }
  if (typeof value === "object" && Object.keys(value as object).length === 0) {
    return "（空）";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

onMounted(async () => {
  void fetchExecutions(true);
  try {
    accounts.value = await listAccounts();
  } catch {
    // 账号过滤项加载失败不阻塞列表
  }
});
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

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.load-more {
  display: flex;
  justify-content: center;
  padding-top: 12px;
}

.detail-body {
  display: flex;
  flex-direction: column;
}

.detail-section-title {
  margin: 16px 0 8px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.detail-json {
  max-height: 280px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  background-color: var(--el-fill-color-light);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
