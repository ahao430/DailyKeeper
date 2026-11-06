<template>
  <div class="agents-page">
    <div class="page-header">
      <h2 class="page-title">执行端管理</h2>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAgents">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreateAgent">新增 Agent</el-button>
      </div>
    </div>

    <el-alert
      class="agent-guide"
      type="info"
      show-icon
      :closable="false"
      title="执行端（dk-agent）是跑在你自己电脑上的任务执行程序"
      description="它把任务延伸到服务器到不了的地方：本地桌面应用、本机浏览器登录态等。拉取式工作——Agent 主动连服务器领任务，服务器不访问你的电脑，家庭网络 NAT 后面即可运行。只有插件声明 requires_agent 的任务才会派发给它（如演示平台的 agent_probe），普通 HTTP/浏览器任务不需要执行端。"
    />
    <el-card shadow="never">
      <el-table v-loading="loading" :data="agents" row-key="id">
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.online ? 'success' : 'info'" size="small">
              {{ row.online ? "在线" : "离线" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="110" align="center">
          <template #default="{ row }">{{ row.version || "-" }}</template>
        </el-table-column>
        <el-table-column label="最近心跳" min-width="160">
          <template #default="{ row }">{{ formatTime(row.last_heartbeat) }}</template>
        </el-table-column>
        <el-table-column prop="running_tasks" label="运行中任务" width="110" align="center" />
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="rotateToken(row)">轮换令牌</el-button>
            <el-button link type="danger" @click="removeAgent(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无 Agent，点击右上角“新增 Agent”创建" :image-size="90" />
        </template>
      </el-table>
    </el-card>

    <!-- 新增 Agent -->
    <el-dialog
      v-model="createDialogVisible"
      title="新增 Agent"
      width="520px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="Agent 名称" prop="name">
          <el-input v-model="form.name" placeholder="Agent 唯一标识，如 my-agent" />
        </el-form-item>
        <el-form-item label="说明">
          <div class="form-help">
            创建后生成访问令牌，令牌仅显示一次，请立即配置到 Agent。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 令牌结果（仅显示一次） -->
    <el-dialog
      v-model="tokenDialogVisible"
      title="Agent 令牌"
      width="560px"
      :close-on-click-modal="false"
    >
      <template v-if="tokenResult">
        <el-alert type="warning" show-icon :closable="false" :title="tokenResult.note" />
        <el-descriptions :column="1" border class="token-meta" size="small">
          <el-descriptions-item label="Agent 名称">{{ tokenResult.name }}</el-descriptions-item>
          <el-descriptions-item label="令牌">
            <el-input :model-value="tokenResult.token" readonly class="token-input">
              <template #append>
                <el-button @click="copyToken">复制</el-button>
              </template>
            </el-input>
          </el-descriptions-item>
        </el-descriptions>
        <div class="token-help">关闭本窗口后将无法再次查看该令牌，请先复制保存。</div>
      </template>
      <template #footer>
        <el-button type="primary" @click="closeTokenDialog">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import dayjs from "dayjs";
import { createAgent, deleteAgent, listAgents, rotateAgent } from "../api";
import { extractErrorMessage } from "../api/client";
import type { AgentInfo } from "../api/types";

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const loading = ref(false);
const agents = ref<AgentInfo[]>([]);

async function loadAgents(): Promise<void> {
  loading.value = true;
  try {
    agents.value = await listAgents();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载 Agent 列表失败"));
  } finally {
    loading.value = false;
  }
}

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm:ss") : value;
}

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

const createDialogVisible = ref(false);
const creating = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({ name: "" });

const rules: FormRules = {
  name: [{ required: true, message: "请输入 Agent 名称", trigger: "blur" }],
};

function openCreateAgent(): void {
  form.name = "";
  createDialogVisible.value = true;
}

async function submitCreate(): Promise<void> {
  if (!formRef.value) {
    return;
  }
  try {
    await formRef.value.validate();
  } catch {
    return;
  }
  creating.value = true;
  try {
    const created = await createAgent({ name: form.name.trim() });
    createDialogVisible.value = false;
    showTokenResult({ name: created.name, token: created.token, note: created.note });
  } catch (error) {
    // 重名等后端校验失败时展示 detail（如“Agent 名称已存在”）
    ElMessage.error(extractErrorMessage(error, "创建 Agent 失败"));
  } finally {
    creating.value = false;
  }
}

// ---------------------------------------------------------------------------
// Token result (shown once)
// ---------------------------------------------------------------------------

interface TokenResult {
  name: string;
  token: string;
  note: string;
}

const tokenDialogVisible = ref(false);
const tokenResult = ref<TokenResult | null>(null);

function showTokenResult(result: TokenResult): void {
  tokenResult.value = result;
  tokenDialogVisible.value = true;
}

function closeTokenDialog(): void {
  tokenDialogVisible.value = false;
  tokenResult.value = null;
  void loadAgents();
}

function legacyCopy(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  document.body.removeChild(textarea);
  return copied;
}

async function copyToken(): Promise<void> {
  const token = tokenResult.value?.token ?? "";
  if (!token) {
    return;
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(token);
      ElMessage.success("令牌已复制到剪贴板");
    } else if (legacyCopy(token)) {
      ElMessage.success("令牌已复制到剪贴板");
    } else {
      ElMessage.error("复制失败，请手动选择令牌复制");
    }
  } catch {
    if (legacyCopy(token)) {
      ElMessage.success("令牌已复制到剪贴板");
    } else {
      ElMessage.error("复制失败，请手动选择令牌复制");
    }
  }
}

// ---------------------------------------------------------------------------
// Rotate & delete
// ---------------------------------------------------------------------------

async function rotateToken(row: AgentInfo): Promise<void> {
  const confirmed = await ElMessageBox.confirm(
    "轮换后旧令牌将立即失效，确定继续？",
    "轮换令牌",
    { type: "warning", confirmButtonText: "轮换", cancelButtonText: "取消" },
  ).catch(() => false);
  if (!confirmed) {
    return;
  }
  try {
    const rotated = await rotateAgent(row.id);
    showTokenResult({ name: row.name, token: rotated.token, note: rotated.note });
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "轮换令牌失败"));
  }
}

async function removeAgent(row: AgentInfo): Promise<void> {
  const confirmed = await ElMessageBox.confirm(
    "删除该 Agent 将中断其运行中的任务，确定删除？",
    `删除 Agent「${row.name}」`,
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
  ).catch(() => false);
  if (!confirmed) {
    return;
  }
  try {
    await deleteAgent(row.id);
    ElMessage.success("Agent 已删除");
    await loadAgents();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "删除 Agent 失败"));
  }
}

onMounted(loadAgents);
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

.agent-guide {
  margin-bottom: 16px;
}

.form-help {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.token-meta {
  margin-top: 16px;
}

.token-input {
  width: 100%;
}

.token-help {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
</style>
