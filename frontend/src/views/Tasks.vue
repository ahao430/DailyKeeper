<template>
  <div class="tasks-page">
    <div class="page-header">
      <h2 class="page-title">任务中心</h2>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" :disabled="!accounts.length" @click="openCreateTask">
          新增任务
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <span class="filter-label">账号</span>
      <el-select
        v-model="filterAccountId"
        clearable
        filterable
        placeholder="全部账号"
        style="width: 240px"
        @change="loadTasks"
      >
        <el-option v-for="account in accounts" :key="account.id" :label="accountLabel(account)" :value="account.id" />
      </el-select>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="tasks" row-key="id">
        <el-table-column prop="account_name" label="账号" min-width="140" show-overflow-tooltip />
        <el-table-column prop="task_name" label="任务" min-width="150" show-overflow-tooltip />
        <el-table-column prop="instance_name" label="平台实例" min-width="130" show-overflow-tooltip />
        <el-table-column label="执行时间" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.time_of_day }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="周期" width="80" align="center">
          <template #default="{ row }">{{ row.interval_days }} 天</template>
        </el-table-column>
        <el-table-column label="启用" width="80" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              @change="(value: string | number | boolean) => toggleEnabled(row, Boolean(value))"
            />
          </template>
        </el-table-column>
        <el-table-column label="下次执行" min-width="150">
          <template #default="{ row }">{{ formatTime(row.next_run_at) }}</template>
        </el-table-column>
        <el-table-column label="最近执行" min-width="150">
          <template #default="{ row }">{{ formatTime(row.last_run_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              :loading="runningId === row.id"
              @click="runNow(row)"
            >
              立即执行
            </el-button>
            <el-button link type="primary" @click="openEditTask(row)">编辑</el-button>
            <el-button link type="danger" @click="removeTask(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无定时任务，点击右上角“新增任务”创建" :image-size="90" />
        </template>
      </el-table>
    </el-card>

    <!-- 新增任务 -->
    <el-dialog v-model="createDialogVisible" title="新增任务" width="640px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="账号" prop="account_id">
          <el-select
            v-model="createForm.account_id"
            filterable
            placeholder="请选择账号"
            style="width: 100%"
            @change="handleCreateAccountChange"
          >
            <el-option v-for="account in accounts" :key="account.id" :label="accountLabel(account)" :value="account.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务类型" prop="task_name">
          <el-select
            v-model="createForm.task_name"
            placeholder="请选择任务"
            :disabled="!taskOptions.length"
            style="width: 100%"
            @change="handleTaskChange"
          >
            <el-option v-for="def in taskOptions" :key="def.name" :label="def.name" :value="def.name">
              <div class="task-option">
                <span>{{ def.name }}</span>
                <el-tag v-if="def.requires_browser" type="warning" size="small">需浏览器</el-tag>
              </div>
              <div class="task-option-desc">{{ def.description }}</div>
            </el-option>
          </el-select>
          <div v-if="!taskOptions.length && createForm.account_id" class="form-hint">
            该账号所属平台暂无可选任务
          </div>
        </el-form-item>
        <el-form-item label="执行时间" prop="time_of_day">
          <el-time-select
            v-model="createForm.time_of_day"
            start="00:00"
            step="00:30"
            end="23:30"
            placeholder="请选择每日执行时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="执行周期" prop="interval_days">
          <el-input-number v-model="createForm.interval_days" :min="1" :max="365" controls-position="right" />
          <span class="form-hint-inline">天</span>
        </el-form-item>
        <el-form-item label="任务参数" prop="params_text">
          <el-input
            v-model="createForm.params_text"
            type="textarea"
            :rows="4"
            placeholder='可选，JSON 对象，如 {"key": "value"}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="createSaving" @click="submitCreate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑任务 -->
    <el-dialog v-model="editDialogVisible" title="编辑任务" width="640px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-form-item label="账号">
          <el-input :model-value="editRowLabel" disabled />
        </el-form-item>
        <el-form-item label="任务类型">
          <el-input :model-value="editRow?.task_name ?? ''" disabled />
        </el-form-item>
        <el-form-item label="执行时间" prop="time_of_day">
          <el-time-select
            v-model="editForm.time_of_day"
            start="00:00"
            step="00:30"
            end="23:30"
            placeholder="请选择每日执行时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="执行周期" prop="interval_days">
          <el-input-number v-model="editForm.interval_days" :min="1" :max="365" controls-position="right" />
          <span class="form-hint-inline">天</span>
        </el-form-item>
        <el-form-item label="任务参数" prop="params_text">
          <el-input
            v-model="editForm.params_text"
            type="textarea"
            :rows="4"
            placeholder='JSON 对象，如 {"key": "value"}，留空表示清空参数'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import dayjs from "dayjs";
import {
  createScheduledTask,
  deleteScheduledTask,
  listAccounts,
  listPlugins,
  listScheduledTasks,
  runScheduledTaskNow,
  updateScheduledTask,
} from "../api";
import { extractErrorMessage } from "../api/client";
import type { Account, ScheduledTask, TaskDefinition } from "../api/types";

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const loading = ref(false);
const accounts = ref<Account[]>([]);
const tasks = ref<ScheduledTask[]>([]);
const filterAccountId = ref<number | undefined>(undefined);
const runningId = ref<number | null>(null);

function accountLabel(account: Account): string {
  const name = account.display_name ? `${account.name}（${account.display_name}）` : account.name;
  return `${account.instance_name} · ${name}`;
}

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm") : value;
}

async function loadTasks(): Promise<void> {
  loading.value = true;
  try {
    tasks.value = await listScheduledTasks(filterAccountId.value ?? undefined);
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载定时任务失败"));
  } finally {
    loading.value = false;
  }
}

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    const [accountList, pluginList] = await Promise.all([listAccounts(), listPlugins()]);
    accounts.value = accountList;
    plugins.value = pluginList;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载任务数据失败"));
  } finally {
    loading.value = false;
  }
  await loadTasks();
}

async function toggleEnabled(row: ScheduledTask, value: boolean): Promise<void> {
  const previous = row.enabled;
  row.enabled = value;
  try {
    await updateScheduledTask(row.id, { enabled: value });
    ElMessage.success(value ? "任务已启用" : "任务已停用");
  } catch (error) {
    row.enabled = previous;
    ElMessage.error(extractErrorMessage(error, "更新任务状态失败"));
  }
  await loadTasks();
}

async function runNow(row: ScheduledTask): Promise<void> {
  runningId.value = row.id;
  try {
    const response = await runScheduledTaskNow(row.id);
    ElMessage.success(response.message);
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "触发执行失败"));
  } finally {
    runningId.value = null;
  }
  await loadTasks();
}

async function removeTask(row: ScheduledTask): Promise<void> {
  const confirmed = await ElMessageBox.confirm(
    `确定删除账号「${row.account_name}」的任务「${row.task_name}」吗？执行历史会保留。`,
    "删除确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
  ).catch(() => false);
  if (!confirmed) {
    return;
  }
  try {
    await deleteScheduledTask(row.id);
    ElMessage.success("定时任务已删除");
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "删除定时任务失败"));
  }
  await loadTasks();
}

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

const plugins = ref<Awaited<ReturnType<typeof listPlugins>>>([]);

const createDialogVisible = ref(false);
const createSaving = ref(false);
const createFormRef = ref<FormInstance>();
const createForm = reactive({
  account_id: undefined as number | undefined,
  task_name: "",
  time_of_day: "08:30",
  interval_days: 1,
  params_text: "",
});

const createRules: FormRules = {
  account_id: [{ required: true, message: "请选择账号", trigger: "change" }],
  task_name: [{ required: true, message: "请选择任务类型", trigger: "change" }],
  time_of_day: [{ required: true, message: "请选择执行时间", trigger: "change" }],
};

const selectedCreateAccount = computed<Account | null>(
  () => accounts.value.find((account) => account.id === createForm.account_id) ?? null,
);

const taskOptions = computed<TaskDefinition[]>(() => {
  const platformId = selectedCreateAccount.value?.platform_id;
  if (!platformId) {
    return [];
  }
  return plugins.value.find((plugin) => plugin.plugin_id === platformId)?.task_definitions ?? [];
});

function openCreateTask(): void {
  createForm.account_id = undefined;
  createForm.task_name = "";
  createForm.time_of_day = "08:30";
  createForm.interval_days = 1;
  createForm.params_text = "";
  createDialogVisible.value = true;
}

function handleCreateAccountChange(): void {
  createForm.task_name = "";
  createForm.time_of_day = "08:30";
  createForm.params_text = "";
}

function handleTaskChange(taskName: string): void {
  const def = taskOptions.value.find((item) => item.name === taskName);
  if (def?.default_time) {
    createForm.time_of_day = def.default_time;
  }
}

async function submitCreate(): Promise<void> {
  const valid = await validateForm(createFormRef.value);
  if (!valid) {
    return;
  }
  const params = parseParamsText(createForm.params_text);
  if (params === null) {
    ElMessage.error("任务参数不是有效的 JSON 对象，请检查后重试");
    return;
  }
  createSaving.value = true;
  try {
    await createScheduledTask({
      account_id: createForm.account_id!,
      task_name: createForm.task_name,
      time_of_day: createForm.time_of_day,
      interval_days: createForm.interval_days,
      params,
    });
    ElMessage.success("定时任务已创建");
    createDialogVisible.value = false;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "创建定时任务失败"));
  } finally {
    createSaving.value = false;
  }
  await loadTasks();
}

// ---------------------------------------------------------------------------
// Edit dialog
// ---------------------------------------------------------------------------

const editDialogVisible = ref(false);
const editSaving = ref(false);
const editFormRef = ref<FormInstance>();
const editRow = ref<ScheduledTask | null>(null);
const editForm = reactive({
  time_of_day: "08:30",
  interval_days: 1,
  params_text: "",
});

const editRules: FormRules = {
  time_of_day: [{ required: true, message: "请选择执行时间", trigger: "change" }],
};

const editRowLabel = computed(() => {
  if (!editRow.value) {
    return "";
  }
  return `${editRow.value.account_name} · ${editRow.value.instance_name}`;
});

function openEditTask(row: ScheduledTask): void {
  editRow.value = row;
  editForm.time_of_day = row.time_of_day;
  editForm.interval_days = row.interval_days;
  const params = row.params ?? {};
  editForm.params_text = Object.keys(params).length ? JSON.stringify(params, null, 2) : "";
  editDialogVisible.value = true;
}

async function submitEdit(): Promise<void> {
  const valid = await validateForm(editFormRef.value);
  if (!valid || !editRow.value) {
    return;
  }
  const params = parseParamsText(editForm.params_text);
  if (params === null) {
    ElMessage.error("任务参数不是有效的 JSON 对象，请检查后重试");
    return;
  }
  editSaving.value = true;
  try {
    await updateScheduledTask(editRow.value.id, {
      time_of_day: editForm.time_of_day,
      interval_days: editForm.interval_days,
      params,
    });
    ElMessage.success("定时任务已更新");
    editDialogVisible.value = false;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "更新定时任务失败"));
  } finally {
    editSaving.value = false;
  }
  await loadTasks();
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/** Parse the params JSON textarea; returns null when invalid, {} when blank. */
function parseParamsText(text: string): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed) {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

async function validateForm(form: FormInstance | undefined): Promise<boolean> {
  if (!form) {
    return false;
  }
  try {
    await form.validate();
    return true;
  } catch {
    return false;
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

.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.filter-label {
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.task-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.task-option-desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}

.form-hint {
  width: 100%;
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.form-hint-inline {
  margin-left: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
