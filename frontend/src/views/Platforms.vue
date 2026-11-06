<template>
  <div class="platforms-page">
    <div class="page-header">
      <h2 class="page-title">平台与账号</h2>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreatePlatform">新增平台</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="instances" row-key="id">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-accounts">
              <div class="expand-header">
                <span class="expand-title">账号（{{ accountsOf(row.id).length }}）</span>
                <el-button
                  size="small"
                  type="primary"
                  :icon="Plus"
                  @click="openCreateAccount(row)"
                >
                  添加账号
                </el-button>
              </div>
              <el-table :data="accountsOf(row.id)" size="small" row-key="id">
                <el-table-column prop="name" label="账号名" min-width="130" show-overflow-tooltip />
                <el-table-column prop="display_name" label="显示名称" min-width="120" show-overflow-tooltip>
                  <template #default="{ row: account }">{{ account.display_name || "-" }}</template>
                </el-table-column>
                <el-table-column label="状态" width="100" align="center">
                  <template #default="{ row: account }">
                    <el-tag :type="statusTagType(account.status)" size="small">{{ statusLabel(account.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="启用" width="70" align="center">
                  <template #default="{ row: account }">
                    <el-switch
                      :model-value="account.enabled"
                      @change="(value: string | number | boolean) => toggleAccount(account, Boolean(value))"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="最近签到" width="110" align="center">
                  <template #default="{ row: account }">{{ account.last_checkin_date || "-" }}</template>
                </el-table-column>
                <el-table-column label="凭据" width="130" align="center">
                  <template #default="{ row: account }">
                    <el-tag v-if="account.has_credential" type="success" size="small">
                      {{ credentialLabel(account.credential_kind) }}
                    </el-tag>
                    <el-tag v-else type="info" size="small">未设置</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="160">
                  <template #default="{ row: account }">
                    <el-button
                      link
                      type="primary"
                      :loading="checkingId === account.id"
                      @click="runCheck(account)"
                    >
                      检测
                    </el-button>
                    <el-button link type="primary" @click="openEditAccount(account)">编辑</el-button>
                    <el-button link type="danger" @click="removeAccount(account)">删除</el-button>
                  </template>
                </el-table-column>
                <template #empty>
                  <el-empty
                    description="还没有账号。账号是登录凭据（用户名/密码/Cookie 等），添加后才能创建定时任务。"
                    :image-size="70"
                  />
                </template>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="实例名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="platform_name" label="平台类型" min-width="130" />
        <el-table-column prop="base_url" label="站点地址" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.base_url || "-" }}</template>
        </el-table-column>
        <el-table-column prop="timezone" label="时区" min-width="130" />
        <el-table-column label="启用" width="70" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              @change="(value: string | number | boolean) => toggleInstance(row, Boolean(value))"
            />
          </template>
        </el-table-column>
        <el-table-column prop="account_count" label="账号数" width="80" align="center" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openEditPlatform(row)">编辑</el-button>
            <el-button link type="danger" @click.stop="removeInstance(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无平台实例，点击右上角“新增平台”创建" :image-size="90" />
        </template>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑平台 -->

    <!-- 添加 / 编辑账号 -->
    <el-dialog
      v-model="accountDialogVisible"
      :title="accountEditing ? '编辑账号' : '添加账号'"
      width="680px"
      destroy-on-close
    >
      <el-form
        ref="accountFormRef"
        :model="accountForm"
        :rules="accountRules"
        label-width="110px"
      >
        <el-form-item label="账号名" prop="name">
          <el-input
            v-model="accountForm.name"
            :disabled="!!accountEditing"
            placeholder="账号唯一标识，如 my-account"
          />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="accountForm.display_name" placeholder="可选，便于识别" />
        </el-form-item>
        <el-form-item label="备注" prop="notes">
          <el-input v-model="accountForm.notes" type="textarea" :rows="2" placeholder="可选备注" />
        </el-form-item>
        <template v-if="activeAccountSchema.length">
          <el-divider content-position="left">账号配置</el-divider>
          <DynamicForm
            :schema="activeAccountSchema"
            :model-value="accountForm.config"
            prefix="config"
            @update:model-value="accountForm.config = $event"
          />
        </template>
        <el-divider content-position="left">登录凭据</el-divider>
        <el-form-item label="凭据类型" prop="credential_kind">
          <el-select v-model="accountForm.credential_kind" style="width: 100%">
            <el-option
              v-for="kind in credentialKindOptions"
              :key="kind.value"
              :label="kind.label"
              :value="kind.value"
            />
          </el-select>
        </el-form-item>
        <template v-if="activeCredentialSchema.length">
          <el-form-item label="凭据字段">
            <DynamicForm
              :schema="activeCredentialSchema"
              :model-value="accountForm.credential_values"
              prefix="credential"
              @update:model-value="accountForm.credential_values = $event"
            />
          </el-form-item>
        </template>
        <el-form-item :label="activeCredentialSchema.length ? '自定义字段' : '凭据内容'">
          <div class="kv-editor">
            <div
              v-for="(row, index) in accountForm.credential_rows"
              :key="index"
              class="kv-row"
            >
              <el-input v-model="row.key" placeholder="字段名，如 cookies" class="kv-key" />
              <el-input
                v-model="row.value"
                :type="isSecretKey(row.key) ? 'password' : 'text'"
                :show-password="isSecretKey(row.key)"
                :placeholder="isSecretKey(row.key) ? '敏感信息（输入时隐藏）' : '字段值'"
                class="kv-value"
              />
              <el-button
                :icon="Delete"
                circle
                text
                type="danger"
                @click="removeCredentialRow(index)"
              />
            </div>
            <div class="kv-toolbar">
              <el-button type="primary" link :icon="Plus" @click="addCredentialRow">
                添加字段
              </el-button>
            </div>
            <div class="kv-help">
              凭据以键值对保存并加密存储（含 token/key/cookie/password 的字段会自动隐藏）。
              {{ accountEditing ? "编辑时留空表示不修改凭据。" : "" }}
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="accountSaving" @click="submitAccount">保存</el-button>
      </template>
    </el-dialog>

    <!-- 凭据检测结果 -->
    <el-dialog v-model="checkDialogVisible" title="凭据检测结果" width="560px">
      <div v-loading="checkLoading" class="check-body">
        <template v-if="checkResult">
          <el-alert
            :type="checkResult.ok ? 'success' : 'error'"
            show-icon
            :closable="false"
            :title="checkResult.message || (checkResult.ok ? '检测通过' : '检测失败')"
          />
          <el-descriptions :column="2" border class="check-meta" size="small">
            <el-descriptions-item label="结果状态">
              <el-tag size="small">{{ checkResult.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="执行记录">
              #{{ checkResult.execution_id }}
            </el-descriptions-item>
          </el-descriptions>
          <div class="check-section-title">返回数据</div>
          <pre class="check-data">{{ prettyData }}</pre>
        </template>
        <div v-else class="check-loading-text">正在执行凭据检测，可能需要数十秒，请稍候…</div>
      </div>
      <template #footer>
        <el-button @click="checkDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import { Delete, Plus, Refresh } from "@element-plus/icons-vue";
import DynamicForm, { buildFormDefaults } from "../components/DynamicForm.vue";
import {
  checkAccount,
  createAccount,
  createPlatform,
  deleteAccount,
  deletePlatform,
  listAccounts,
  listPlatforms,
  listPlugins,
  updateAccount,
  updatePlatform,
} from "../api";
import { extractErrorMessage } from "../api/client";
import type {
  Account,
  CheckResponse,
  FieldDef,
  PlatformInstance,
  PluginManifest,
} from "../api/types";

const TIMEZONES = [
  "Asia/Shanghai",
  "UTC",
  "Asia/Tokyo",
  "Asia/Hong_Kong",
  "America/New_York",
  "Europe/London",
];

const CREDENTIAL_KINDS = [
  { value: "cookie", label: "Cookie" },
  { value: "token", label: "Token" },
  { value: "api_key", label: "API Key" },
  { value: "username_password", label: "用户名密码" },
  { value: "browser_session", label: "浏览器会话" },
];

const STATUS_TAG_TYPES: Record<string, "success" | "warning" | "info"> = {
  ACTIVE: "success",
  AUTH_EXPIRED: "warning",
  DISABLED: "info",
};

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "活跃",
  AUTH_EXPIRED: "凭证失效",
  DISABLED: "已停用",
};

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const loading = ref(false);
const plugins = ref<PluginManifest[]>([]);
const instances = ref<PlatformInstance[]>([]);
const accounts = ref<Account[]>([]);
const checkingId = ref<number | null>(null);

function accountsOf(instanceId: number): Account[] {
  return accounts.value.filter((account) => account.instance_id === instanceId);
}

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    const [pluginList, platformList, accountList] = await Promise.all([
      listPlugins(),
      listPlatforms(),
      listAccounts(),
    ]);
    plugins.value = pluginList;
    instances.value = platformList;
    accounts.value = accountList;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载平台数据失败"));
  } finally {
    loading.value = false;
  }
}

async function refreshAccounts(): Promise<void> {
  try {
    accounts.value = await listAccounts();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载账号数据失败"));
  }
}

function statusTagType(status: string): "success" | "warning" | "info" {
  return STATUS_TAG_TYPES[status] ?? "info";
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function credentialLabel(kind: string | null): string {
  return CREDENTIAL_KINDS.find((item) => item.value === kind)?.label ?? (kind || "已设置");
}

async function toggleInstance(row: PlatformInstance, value: boolean): Promise<void> {
  try {
    const updated = await updatePlatform(row.id, { enabled: value });
    const index = instances.value.findIndex((item) => item.id === row.id);
    if (index >= 0) {
      instances.value[index] = { ...instances.value[index], ...updated };
    }
    ElMessage.success(value ? "已启用" : "已停用");
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "更新平台状态失败"));
    await loadAll();
  }
}

async function toggleAccount(row: Account, value: boolean): Promise<void> {
  try {
    const updated = await updateAccount(row.id, { enabled: value });
    const index = accounts.value.findIndex((item) => item.id === row.id);
    if (index >= 0) {
      accounts.value[index] = { ...accounts.value[index], ...updated };
    }
    ElMessage.success(value ? "已启用" : "已停用");
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "更新账号状态失败"));
    await refreshAccounts();
  }
}

async function removeInstance(row: PlatformInstance): Promise<void> {
  const confirmed = await ElMessageBox.confirm(
    `确定删除平台实例「${row.name}」吗？删除后不可恢复。`,
    "删除确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
  ).catch(() => false);
  if (!confirmed) {
    return;
  }
  try {
    await deletePlatform(row.id);
    ElMessage.success("平台实例已删除");
    await loadAll();
  } catch (error) {
    // 409 等后端校验失败时展示 detail（如“该平台实例下仍有账号，请先删除账号”）
    ElMessage.error(extractErrorMessage(error, "删除平台实例失败"));
  }
}

// ---------------------------------------------------------------------------
// Platform dialog
// ---------------------------------------------------------------------------

const platformDialogVisible = ref(false);
const platformSaving = ref(false);
const platformFormRef = ref<FormInstance>();
const platformEditing = ref<PlatformInstance | null>(null);
const platformForm = reactive({
  platform_id: "",
  name: "",
  base_url: "",
  timezone: "Asia/Shanghai",
  description: "",
  config: {} as Record<string, unknown>,
});

const platformRules: FormRules = {
  platform_id: [{ required: true, message: "请选择平台类型", trigger: "change" }],
  name: [{ required: true, message: "请输入实例名称", trigger: "blur" }],
  timezone: [{ required: true, message: "请选择时区", trigger: "change" }],
};

const activePlatformPlugin = computed<PluginManifest | null>(() => {
  const targetId = platformEditing.value?.platform_id ?? platformForm.platform_id;
  return plugins.value.find((plugin) => plugin.plugin_id === targetId) ?? null;
});

const activePlatformSchema = computed<FieldDef[]>(() => activePlatformPlugin.value?.config_schema ?? []);

function openCreatePlatform(): void {
  platformEditing.value = null;
  platformForm.platform_id = "";
  platformForm.name = "";
  platformForm.base_url = "";
  platformForm.timezone = "Asia/Shanghai";
  platformForm.description = "";
  platformForm.config = {};
  platformDialogVisible.value = true;
}

function openEditPlatform(row: PlatformInstance): void {
  platformEditing.value = row;
  platformForm.platform_id = row.platform_id;
  platformForm.name = row.name;
  platformForm.base_url = row.base_url;
  platformForm.timezone = row.timezone || "Asia/Shanghai";
  platformForm.description = row.description;
  platformForm.config = { ...row.config };
  platformDialogVisible.value = true;
}

function handlePluginChange(pluginId: string): void {
  const plugin = plugins.value.find((item) => item.plugin_id === pluginId);
  platformForm.config = plugin ? buildFormDefaults(plugin.config_schema) : {};
}

async function submitPlatform(): Promise<void> {
  const valid = await validateForm(platformFormRef.value);
  if (!valid) {
    return;
  }
  platformSaving.value = true;
  try {
    if (platformEditing.value) {
      const updated = await updatePlatform(platformEditing.value.id, {
        name: platformForm.name.trim(),
        base_url: platformForm.base_url.trim(),
        timezone: platformForm.timezone,
        description: platformForm.description,
        config: platformForm.config,
      });
      const index = instances.value.findIndex((item) => item.id === updated.id);
      if (index >= 0) {
        instances.value[index] = updated;
      }
      ElMessage.success("平台实例已更新");
    } else {
      const created = await createPlatform({
        platform_id: platformForm.platform_id,
        name: platformForm.name.trim(),
        base_url: platformForm.base_url.trim(),
        timezone: platformForm.timezone,
        description: platformForm.description,
        config: platformForm.config,
        enabled: true,
      });
      instances.value.push(created);
      ElMessage.success("平台实例已创建，展开该行即可添加账号");
    }
    platformDialogVisible.value = false;
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "保存平台实例失败"));
  } finally {
    platformSaving.value = false;
  }
}

// ---------------------------------------------------------------------------
// Account dialog
// ---------------------------------------------------------------------------

interface CredentialRow {
  key: string;
  value: string;
}

const accountDialogVisible = ref(false);
const accountSaving = ref(false);
const accountFormRef = ref<FormInstance>();
const accountEditing = ref<Account | null>(null);
const accountInstanceId = ref<number | null>(null);
const accountForm = reactive({
  name: "",
  display_name: "",
  notes: "",
  config: {} as Record<string, unknown>,
  credential_kind: "cookie",
  credential_values: {} as Record<string, unknown>,
  credential_rows: [{ key: "", value: "" }] as CredentialRow[],
});

const accountRules = computed<FormRules>(() => ({
  name: [{ required: true, message: "请输入账号名", trigger: "blur" }],
  credential_kind: [{ required: true, message: "请选择凭据类型", trigger: "change" }],
}));

const activeAccountPlugin = computed<PluginManifest | null>(() => {
  const platformId =
    accountEditing.value?.platform_id ??
    instances.value.find((item) => item.id === accountInstanceId.value)?.platform_id;
  return plugins.value.find((plugin) => plugin.plugin_id === platformId) ?? null;
});

const activeAccountSchema = computed<FieldDef[]>(() => activeAccountPlugin.value?.account_schema ?? []);
const activeCredentialSchema = computed<FieldDef[]>(
  () => activeAccountPlugin.value?.credential_schema ?? [],
);

const credentialKindOptions = computed(() => {
  const allowed = activeAccountPlugin.value?.auth_types ?? [];
  const filtered = CREDENTIAL_KINDS.filter((kind) => allowed.includes(kind.value));
  // 插件声明了未知类型（如 demo 的 "none"）或未声明时，回退全量列表避免下拉为空
  return filtered.length ? filtered : CREDENTIAL_KINDS;
});

function isSecretKey(key: string): boolean {
  return /token|key|cookie|password|secret/i.test(key);
}

function addCredentialRow(): void {
  accountForm.credential_rows.push({ key: "", value: "" });
}

function removeCredentialRow(index: number): void {
  accountForm.credential_rows.splice(index, 1);
}

function openCreateAccount(instance: PlatformInstance): void {
  accountInstanceId.value = instance.id;
  accountEditing.value = null;
  accountForm.name = "";
  accountForm.display_name = "";
  accountForm.notes = "";
  accountForm.config = buildFormDefaults(activeAccountSchema.value);
  accountForm.credential_kind = credentialKindOptions.value[0]?.value ?? "cookie";
  accountForm.credential_values = buildFormDefaults(activeCredentialSchema.value);
  accountForm.credential_rows = [{ key: "", value: "" }];
  accountDialogVisible.value = true;
}

function openEditAccount(row: Account): void {
  accountInstanceId.value = row.instance_id;
  accountEditing.value = row;
  accountForm.name = row.name;
  accountForm.display_name = row.display_name;
  accountForm.notes = row.notes;
  accountForm.config = { ...row.config };
  accountForm.credential_kind = row.credential_kind ?? credentialKindOptions.value[0]?.value ?? "cookie";
  // 凭据明文不出后端，编辑时空值表示不修改
  accountForm.credential_values = buildFormDefaults(activeCredentialSchema.value);
  accountForm.credential_rows = [{ key: "", value: "" }];
  accountDialogVisible.value = true;
}

function buildCredentialData(): Record<string, string> {
  const data: Record<string, string> = {};
  for (const field of activeCredentialSchema.value) {
    const value = accountForm.credential_values[field.name];
    if (value !== undefined && value !== null && String(value) !== "") {
      data[field.name] = String(value);
    }
  }
  for (const row of accountForm.credential_rows) {
    const key = row.key.trim();
    if (key) {
      data[key] = row.value;
    }
  }
  return data;
}

async function submitAccount(): Promise<void> {
  const valid = await validateForm(accountFormRef.value);
  if (!valid) {
    return;
  }
  if (!accountInstanceId.value && !accountEditing.value) {
    ElMessage.warning("缺少账号所属的平台实例");
    return;
  }
  accountSaving.value = true;
  try {
    const credentialData = buildCredentialData();
    const hasCredentialInput = Object.keys(credentialData).length > 0;
    if (accountEditing.value) {
      const updated = await updateAccount(accountEditing.value.id, {
        display_name: accountForm.display_name,
        notes: accountForm.notes,
        config: accountForm.config,
        ...(hasCredentialInput
          ? { credential: { kind: accountForm.credential_kind, data: credentialData } }
          : {}),
      });
      const index = accounts.value.findIndex((item) => item.id === updated.id);
      if (index >= 0) {
        accounts.value[index] = updated;
      }
      ElMessage.success("账号已更新");
    } else {
      const created = await createAccount({
        instance_id: accountInstanceId.value!,
        name: accountForm.name.trim(),
        display_name: accountForm.display_name,
        config: accountForm.config,
        credential: { kind: accountForm.credential_kind, data: credentialData },
      });
      // 后端创建接口不含 notes，非空时补充更新一次
      if (accountForm.notes) {
        await updateAccount(created.id, { notes: accountForm.notes });
      }
      await refreshAccounts();
      ElMessage.success("账号已创建");
    }
    accountDialogVisible.value = false;
    // 账号数量变化后刷新实例列表中的 account_count
    instances.value = await listPlatforms();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "保存账号失败"));
  } finally {
    accountSaving.value = false;
  }
}

async function removeAccount(row: Account): Promise<void> {
  const confirmed = await ElMessageBox.confirm(
    `确定删除账号「${row.name}」吗？其执行记录、资源快照与定时任务将一并删除，不可恢复。`,
    "删除确认",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
  ).catch(() => false);
  if (!confirmed) {
    return;
  }
  try {
    await deleteAccount(row.id);
    ElMessage.success("账号已删除");
    await refreshAccounts();
    instances.value = await listPlatforms();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "删除账号失败"));
  }
}

// ---------------------------------------------------------------------------
// Credential check
// ---------------------------------------------------------------------------

const checkDialogVisible = ref(false);
const checkLoading = ref(false);
const checkResult = ref<CheckResponse | null>(null);

const prettyData = computed(() => {
  if (!checkResult.value) {
    return "";
  }
  const data = checkResult.value.data;
  if (data === undefined || data === null || (typeof data === "object" && Object.keys(data as object).length === 0)) {
    return "（无返回数据）";
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
});

async function runCheck(row: Account): Promise<void> {
  checkingId.value = row.id;
  checkResult.value = null;
  checkDialogVisible.value = true;
  checkLoading.value = true;
  try {
    checkResult.value = await checkAccount(row.id);
  } catch (error) {
    checkDialogVisible.value = false;
    ElMessage.error(extractErrorMessage(error, "凭据检测失败"));
  } finally {
    checkLoading.value = false;
    checkingId.value = null;
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

.expand-accounts {
  padding: 4px 12px 12px 48px;
}

.expand-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.expand-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.kv-editor {
  width: 100%;
  display: block;
}

.kv-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.kv-key {
  width: 180px;
  flex-shrink: 0;
}

.kv-value {
  flex: 1;
}

.kv-toolbar {
  margin-bottom: 4px;
}

.kv-help {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.check-body {
  min-height: 120px;
}

.check-loading-text {
  padding: 24px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.check-meta {
  margin-top: 16px;
}

.check-section-title {
  margin: 16px 0 8px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.check-data {
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
