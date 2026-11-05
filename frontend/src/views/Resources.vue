<template>
  <div class="resources-page">
    <div class="page-header">
      <h2 class="page-title">资源看板</h2>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
      </div>
    </div>

    <!-- 资源总览 -->
    <el-card shadow="never" class="overview-card">
      <template #header>
        <span class="card-title">资源总览</span>
      </template>
      <template v-if="summaryGroups.length">
        <div v-for="group in summaryGroups" :key="group.account_id" class="overview-group">
          <div class="overview-group-header">
            <span class="overview-account">{{ group.account_name }}</span>
            <el-tag size="small" type="info">{{ group.instance_name }}</el-tag>
          </div>
          <el-table :data="group.items" size="small">
            <el-table-column label="资源类型" min-width="120">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ resourceLabel(row.resource_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数值" min-width="140">
              <template #default="{ row }">
                <span class="overview-value">{{ displayValue(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="单位" width="100" align="center">
              <template #default="{ row }">{{ row.unit || "-" }}</template>
            </el-table-column>
            <el-table-column label="采集时间" min-width="160">
              <template #default="{ row }">{{ formatTime(row.observed_at) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </template>
      <el-empty v-else-if="!loading" description="暂无资源数据，任务执行后自动采集" :image-size="90" />
    </el-card>

    <!-- 趋势 -->
    <el-card shadow="never" class="trend-card">
      <template #header>
        <div class="trend-header">
          <span class="card-title">趋势</span>
          <div class="trend-filters">
            <el-select
              v-model="trendAccountId"
              filterable
              placeholder="账号"
              style="width: 220px"
              @change="onTrendAccountChange"
            >
              <el-option
                v-for="group in summaryGroups"
                :key="group.account_id"
                :label="group.account_name"
                :value="group.account_id"
              />
            </el-select>
            <el-select v-model="trendResourceType" placeholder="资源类型" style="width: 160px">
              <el-option
                v-for="option in trendTypeOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-button type="primary" :loading="trendLoading" @click="loadTrend">查询</el-button>
          </div>
        </div>
      </template>
      <el-empty v-if="trendEmpty && !trendLoading" description="该资源暂无数值型快照" :image-size="90" />
      <div v-else ref="trendChartRef" v-loading="trendLoading" class="trend-chart"></div>
    </el-card>

    <!-- 快照记录 -->
    <el-card shadow="never" class="snapshots-card">
      <template #header>
        <div class="snapshots-header">
          <span class="card-title">快照记录</span>
          <div class="snapshots-filters">
            <el-select v-model="snapshotAccountId" clearable filterable placeholder="账号" style="width: 200px" @change="reloadSnapshots">
              <el-option v-for="account in accounts" :key="account.id" :label="accountLabel(account)" :value="account.id" />
            </el-select>
            <el-select v-model="snapshotResourceType" clearable placeholder="资源类型" style="width: 160px" @change="reloadSnapshots">
              <el-option v-for="type in RESOURCE_TYPE_OPTIONS" :key="type.value" :label="type.label" :value="type.value" />
            </el-select>
          </div>
        </div>
      </template>
      <el-table v-loading="snapshotsLoading" :data="snapshots" row-key="id" size="small">
        <el-table-column prop="account_name" label="账号" min-width="140" show-overflow-tooltip />
        <el-table-column label="资源类型" min-width="110">
          <template #default="{ row }">{{ resourceLabel(row.resource_type) }}</template>
        </el-table-column>
        <el-table-column label="数值" min-width="140">
          <template #default="{ row }">{{ displayValue(row) }}</template>
        </el-table-column>
        <el-table-column label="单位" width="90" align="center">
          <template #default="{ row }">{{ row.unit || "-" }}</template>
        </el-table-column>
        <el-table-column label="采集时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.observed_at) }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.source || "-" }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无快照记录" :image-size="80" />
        </template>
      </el-table>
      <div v-if="hasMoreSnapshots" class="load-more">
        <el-button :loading="snapshotsLoading" @click="loadMoreSnapshots">加载更多</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import dayjs from "dayjs";
import { getResourceSummary, listAccounts, listResources } from "../api";
import { extractErrorMessage } from "../api/client";
import type { Account, ResourceSnapshot, ResourceSummary } from "../api/types";
import { RESOURCE_LABELS, resourceLabel } from "../constants/labels";

const SNAPSHOT_PAGE = 100;

const RESOURCE_TYPE_OPTIONS = Object.entries(RESOURCE_LABELS).map(([value, label]) => ({ value, label }));

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const loading = ref(false);
const accounts = ref<Account[]>([]);
const summary = ref<ResourceSummary[]>([]);

const snapshotsLoading = ref(false);
const snapshots = ref<ResourceSnapshot[]>([]);
const snapshotAccountId = ref<number | undefined>(undefined);
const snapshotResourceType = ref("");
const snapshotLimit = ref(SNAPSHOT_PAGE);
const hasMoreSnapshots = ref(false);

interface SummaryGroup {
  account_id: number;
  account_name: string;
  instance_name: string;
  items: ResourceSummary[];
}

const summaryGroups = computed<SummaryGroup[]>(() => {
  const map = new Map<number, SummaryGroup>();
  for (const item of summary.value) {
    let group = map.get(item.account_id);
    if (!group) {
      group = {
        account_id: item.account_id,
        account_name: item.account_name,
        instance_name: item.instance_name,
        items: [],
      };
      map.set(item.account_id, group);
    }
    group.items.push(item);
  }
  return [...map.values()];
});

function accountLabel(account: Account): string {
  return account.display_name ? `${account.name}（${account.display_name}）` : account.name;
}

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm") : value;
}

/** 优先展示文本值（如网址类资源），否则展示数值。 */
function displayValue(item: { value: number | null; text_value: string | null }): string {
  if (item.text_value !== null && item.text_value !== "") {
    return item.text_value;
  }
  if (item.value !== null) {
    return String(item.value);
  }
  return "-";
}

async function loadSummary(): Promise<void> {
  try {
    summary.value = await getResourceSummary();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载资源总览失败"));
  }
}

async function loadSnapshots(): Promise<void> {
  snapshotsLoading.value = true;
  try {
    const page = await listResources({
      account_id: snapshotAccountId.value ?? undefined,
      resource_type: snapshotResourceType.value || undefined,
      limit: snapshotLimit.value,
    });
    snapshots.value = page;
    hasMoreSnapshots.value = page.length === snapshotLimit.value;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载快照记录失败"));
  } finally {
    snapshotsLoading.value = false;
  }
}

function reloadSnapshots(): void {
  snapshotLimit.value = SNAPSHOT_PAGE;
  void loadSnapshots();
}

function loadMoreSnapshots(): void {
  // 后端 limit 上限 500（le=500）
  snapshotLimit.value = Math.min(snapshotLimit.value + SNAPSHOT_PAGE, 500);
  void loadSnapshots();
}

// ---------------------------------------------------------------------------
// Trend chart (趋势)
// ---------------------------------------------------------------------------

const TREND_LIMIT = 200;

const trendLoading = ref(false);
const trendAccountId = ref<number | undefined>(undefined);
const trendResourceType = ref("");
const trendPoints = ref<(ResourceSnapshot & { value: number })[]>([]);
const trendChartRef = ref<HTMLDivElement | null>(null);
let trendChart: ReturnType<typeof echarts.init> | null = null;

const trendTypeOptions = computed<{ value: string; label: string }[]>(() => {
  const group = summaryGroups.value.find((item) => item.account_id === trendAccountId.value);
  if (!group) {
    return [];
  }
  const types = [...new Set(group.items.map((item) => item.resource_type))];
  return types.map((type) => ({ value: type, label: resourceLabel(type) }));
});

const trendEmpty = computed(() => trendPoints.value.length === 0);

watch([trendAccountId, trendResourceType], () => {
  void loadTrend();
});

function onTrendAccountChange(): void {
  const options = trendTypeOptions.value;
  if (options.length && !options.some((option) => option.value === trendResourceType.value)) {
    trendResourceType.value = options[0].value;
  }
  // watch([trendAccountId, trendResourceType]) 会触发重新查询
}

/** 挂载后总览加载完成时，默认选中第一个账号与其第一个资源类型（由 watch 触发查询）。 */
function initTrendSelection(): void {
  const firstGroup = summaryGroups.value[0];
  if (!firstGroup) {
    return;
  }
  if (trendAccountId.value === undefined) {
    trendAccountId.value = firstGroup.account_id;
  }
  if (!trendResourceType.value) {
    const options = trendTypeOptions.value;
    if (options.length) {
      trendResourceType.value = options[0].value;
    }
  }
}

async function loadTrend(): Promise<void> {
  if (trendAccountId.value === undefined || !trendResourceType.value) {
    trendPoints.value = [];
    return;
  }
  trendLoading.value = true;
  try {
    const page = await listResources({
      account_id: trendAccountId.value,
      resource_type: trendResourceType.value,
      limit: TREND_LIMIT,
    });
    trendPoints.value = page
      .filter((item): item is ResourceSnapshot & { value: number } => item.value !== null)
      .sort((a, b) => dayjs(a.observed_at).valueOf() - dayjs(b.observed_at).valueOf());
    await nextTick();
    renderTrend();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载趋势数据失败"));
  } finally {
    trendLoading.value = false;
  }
}

function renderTrend(): void {
  const el = trendChartRef.value;
  if (!el) {
    return;
  }
  // el-empty 与图表互斥切换后 DOM 节点会被重建，旧实例需先销毁
  if (trendChart && trendChart.getDom() !== el) {
    trendChart.dispose();
    trendChart = null;
  }
  if (!trendChart) {
    trendChart = echarts.init(el);
  }
  const type = trendResourceType.value;
  const summaryItem = summary.value.find(
    (item) => item.account_id === trendAccountId.value && item.resource_type === type,
  );
  const unit = summaryItem?.unit ?? trendPoints.value[0]?.unit ?? null;
  const option: echarts.EChartsOption = {
    tooltip: { trigger: "axis" },
    grid: { left: 12, right: 20, top: 24, bottom: 12, containLabel: true },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true },
    series: [
      {
        name: `${resourceLabel(type)}（${unit || "-"}）`,
        type: "line",
        smooth: true,
        color: "#409eff",
        data: trendPoints.value.map((item) => [item.observed_at, item.value]),
        areaStyle: { opacity: 0.15 },
      },
    ],
  };
  trendChart.setOption(option, true);
}

function handleTrendResize(): void {
  trendChart?.resize();
}

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    accounts.value = await listAccounts();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载账号数据失败"));
  } finally {
    loading.value = false;
  }
  await Promise.all([loadSummary(), loadSnapshots()]);
}

onMounted(async () => {
  window.addEventListener("resize", handleTrendResize);
  await loadAll();
  initTrendSelection();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleTrendResize);
  trendChart?.dispose();
  trendChart = null;
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

.card-title {
  font-weight: 600;
}

.overview-card {
  margin-bottom: 16px;
}

.overview-group {
  margin-bottom: 8px;
}

.overview-group:last-child {
  margin-bottom: 0;
}

.overview-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.overview-value {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.trend-card {
  margin-bottom: 16px;
}

.trend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.trend-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trend-chart {
  width: 100%;
  height: 320px;
}

.snapshots-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.snapshots-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.load-more {
  display: flex;
  justify-content: center;
  padding-top: 12px;
}
</style>
