<template>
  <div class="settings-page">
    <!-- 通知设置 -->
    <el-card v-loading="notifyLoading" shadow="never" class="settings-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">通知设置</span>
          <div class="notify-enabled">
            <span>启用通知</span>
            <el-switch v-model="notifyForm.enabled" />
          </div>
        </div>
      </template>

      <div class="section-subtitle">事件开关</div>
      <el-table :data="eventRows" size="small" class="events-table">
        <el-table-column prop="label" label="事件" min-width="160" />
        <el-table-column prop="key" label="标识" min-width="140">
          <template #default="{ row }">
            <span class="event-key">{{ row.key }}</span>
          </template>
        </el-table-column>
        <el-table-column label="通知" width="100" align="center">
          <template #default="{ row }">
            <el-switch v-model="notifyForm.events[row.key].enabled" />
          </template>
        </el-table-column>
      </el-table>

      <div class="section-subtitle channels-subtitle">通知渠道</div>
      <el-table :data="notifyForm.channels" size="small">
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ channelTypeLabel(row.type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="启用" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row, $index }">
            <el-button
              link
              type="primary"
              :loading="testingIndex === $index"
              @click="testChannel(row, $index)"
            >
              测试
            </el-button>
            <el-button link type="danger" @click="removeChannel($index)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无通知渠道，点击“添加渠道”创建" :image-size="80" />
        </template>
      </el-table>
      <div class="channel-toolbar">
        <el-button type="primary" plain :icon="Plus" @click="openAddChannel">添加渠道</el-button>
      </div>

      <div class="save-bar">
        <el-button type="primary" :loading="notifySaving" @click="saveNotifications">保存设置</el-button>
      </div>
    </el-card>

    <!-- 修改密码 -->
    <el-card shadow="never" class="settings-card">
      <template #header>
        <span class="card-title">修改密码</span>
      </template>
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="100px"
        style="max-width: 480px"
      >
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入原密码" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="passwordForm.confirm_password" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="passwordSaving" @click="submitPassword">修改密码</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 添加渠道 -->
    <el-dialog v-model="channelDialogVisible" title="添加渠道" width="560px" destroy-on-close>
      <el-form ref="channelFormRef" :model="channelForm" :rules="channelRules" label-width="100px">
        <el-form-item label="渠道类型" prop="type">
          <el-select v-model="channelForm.type" placeholder="请选择渠道类型" style="width: 100%" @change="handleChannelTypeChange">
            <el-option v-for="item in CHANNEL_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="渠道名称" prop="name">
          <el-input v-model="channelForm.name" placeholder="便于识别的名称，如 我的 iPhone" />
        </el-form-item>
        <template v-if="activeChannelSchema.length">
          <el-divider content-position="left">渠道配置</el-divider>
          <DynamicForm
            :schema="activeChannelSchema"
            :model-value="channelForm.config"
            prefix="config"
            @update:model-value="channelForm.config = $event"
          />
        </template>
      </el-form>
      <template #footer>
        <el-button @click="channelDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitChannel">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import DynamicForm, { buildFormDefaults } from "../components/DynamicForm.vue";
import {
  changePassword,
  getSystemSettings,
  testNotification,
  updateNotificationSettings,
} from "../api";
import { extractErrorMessage } from "../api/client";
import type { FieldDef, NotificationChannelSpec } from "../api/types";

// ---------------------------------------------------------------------------
// Notification settings
// ---------------------------------------------------------------------------

const EVENT_ITEMS = [
  { key: "task_success", label: "任务成功" },
  { key: "task_failed", label: "任务失败" },
  { key: "auth_expired", label: "登录失效" },
  { key: "needs_action", label: "需要人工处理" },
  { key: "rate_limited", label: "触发限流" },
  { key: "resource_low", label: "余额低于阈值" },
  { key: "agent_offline", label: "Agent 离线" },
];

const CHANNEL_TYPE_OPTIONS = [
  { value: "bark", label: "Bark" },
  { value: "gotify", label: "Gotify" },
  { value: "webhook", label: "Webhook" },
];

/** Per-type config schemas for the 添加渠道 dialog (dailykeeper_sdk FieldDef shapes). */
const CHANNEL_SCHEMAS: Record<string, FieldDef[]> = {
  bark: [
    {
      name: "server",
      label: "服务器地址",
      type: "string",
      required: false,
      default: "https://api.day.app",
      options: null,
      help: "自建 Bark 服务时填写，默认官方地址",
      placeholder: "https://api.day.app",
    },
    {
      name: "device_key",
      label: "Device Key",
      type: "string",
      required: true,
      default: "",
      options: null,
      help: "",
      placeholder: "Bark App 中的设备 Key",
    },
  ],
  gotify: [
    {
      name: "server",
      label: "服务器地址",
      type: "string",
      required: true,
      default: "",
      options: null,
      help: "",
      placeholder: "https://gotify.example.com",
    },
    {
      name: "token",
      label: "应用 Token",
      type: "string",
      required: true,
      default: "",
      options: null,
      help: "",
      placeholder: "Gotify 应用的 Token",
    },
  ],
  webhook: [
    {
      name: "url",
      label: "Webhook 地址",
      type: "string",
      required: true,
      default: "",
      options: null,
      help: "POST JSON {title, body, timestamp}",
      placeholder: "https://example.com/hook",
    },
  ],
};

const notifyLoading = ref(false);
const notifySaving = ref(false);
const testingIndex = ref<number | null>(null);

const notifyForm = reactive({
  enabled: true,
  channels: [] as NotificationChannelSpec[],
  events: Object.fromEntries(EVENT_ITEMS.map((item) => [item.key, { enabled: false }])) as Record<
    string,
    { enabled: boolean }
  >,
  thresholds: {} as Record<string, unknown>,
});

const eventRows = computed(() =>
  EVENT_ITEMS.map((item) => ({ key: item.key, label: item.label })),
);

function channelTypeLabel(type: string): string {
  return CHANNEL_TYPE_OPTIONS.find((item) => item.value === type)?.label ?? type;
}

async function loadSettings(): Promise<void> {
  notifyLoading.value = true;
  try {
    const settings = await getSystemSettings();
    notifyForm.enabled = settings.notifications.enabled;
    notifyForm.channels = (settings.notifications.channels ?? []).map((channel) => ({
      ...channel,
      enabled: channel.enabled ?? true,
    }));
    for (const item of EVENT_ITEMS) {
      const current = settings.notifications.events?.[item.key];
      notifyForm.events[item.key] = { enabled: current?.enabled ?? false };
    }
    notifyForm.thresholds = settings.notifications.thresholds ?? {};
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载系统设置失败"));
  } finally {
    notifyLoading.value = false;
  }
}

async function saveNotifications(): Promise<void> {
  notifySaving.value = true;
  try {
    await updateNotificationSettings({
      enabled: notifyForm.enabled,
      channels: notifyForm.channels,
      events: notifyForm.events,
      thresholds: notifyForm.thresholds,
    });
    ElMessage.success("通知设置已保存");
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "保存通知设置失败"));
  } finally {
    notifySaving.value = false;
  }
}

async function testChannel(row: NotificationChannelSpec, index: number): Promise<void> {
  testingIndex.value = index;
  try {
    const result = await testNotification({ type: row.type, name: row.name, config: row.config });
    if (result.ok) {
      ElMessage.success(`测试通知已发送到「${row.name}」，请注意查收`);
    } else {
      ElMessage.error(result.error || "测试通知发送失败");
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "测试通知发送失败"));
  } finally {
    testingIndex.value = null;
  }
}

function removeChannel(index: number): void {
  notifyForm.channels.splice(index, 1);
}

// 添加渠道 dialog
const channelDialogVisible = ref(false);
const channelFormRef = ref<FormInstance>();
const channelForm = reactive({
  type: "",
  name: "",
  config: {} as Record<string, unknown>,
});

// 渠道 config 字段的必填校验由 DynamicForm 按 schema 自带
const channelRules: FormRules = {
  type: [{ required: true, message: "请选择渠道类型", trigger: "change" }],
  name: [{ required: true, message: "请输入渠道名称", trigger: "blur" }],
};

const activeChannelSchema = computed<FieldDef[]>(() => CHANNEL_SCHEMAS[channelForm.type] ?? []);

function openAddChannel(): void {
  channelForm.type = "";
  channelForm.name = "";
  channelForm.config = {};
  channelDialogVisible.value = true;
}

function handleChannelTypeChange(type: string): void {
  const schema = CHANNEL_SCHEMAS[type] ?? [];
  channelForm.config = schema.length ? buildFormDefaults(schema) : {};
}

async function submitChannel(): Promise<void> {
  const valid = await validateForm(channelFormRef.value);
  if (!valid) {
    return;
  }
  notifyForm.channels.push({
    type: channelForm.type,
    name: channelForm.name.trim(),
    config: channelForm.config,
    enabled: true,
  });
  channelDialogVisible.value = false;
  ElMessage.success("渠道已添加，记得点击“保存设置”生效");
}

// ---------------------------------------------------------------------------
// Password form
// ---------------------------------------------------------------------------

const passwordSaving = ref(false);
const passwordFormRef = ref<FormInstance>();
const passwordForm = reactive({
  old_password: "",
  new_password: "",
  confirm_password: "",
});

const passwordRules: FormRules = {
  old_password: [{ required: true, message: "请输入原密码", trigger: "blur" }],
  new_password: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 6, message: "新密码至少 6 位", trigger: "blur" },
  ],
  confirm_password: [
    { required: true, message: "请再次输入新密码", trigger: "blur" },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== passwordForm.new_password) {
          callback(new Error("两次输入的密码不一致"));
        } else {
          callback();
        }
      },
      trigger: "blur",
    },
  ],
};

async function submitPassword(): Promise<void> {
  const valid = await validateForm(passwordFormRef.value);
  if (!valid) {
    return;
  }
  passwordSaving.value = true;
  try {
    await changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    });
    ElMessage.success("密码已修改");
    passwordForm.old_password = "";
    passwordForm.new_password = "";
    passwordForm.confirm_password = "";
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "修改密码失败"));
  } finally {
    passwordSaving.value = false;
  }
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

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

onMounted(loadSettings);
</script>

<style scoped>
.settings-page {
  max-width: 960px;
}

.settings-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
}

.notify-enabled {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.section-subtitle {
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.channels-subtitle {
  margin-top: 20px;
}

.event-key {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.channel-toolbar {
  margin-top: 8px;
}

.save-bar {
  margin-top: 16px;
}
</style>
