<template>
  <div class="registry-page">
    <div class="page-header">
      <h2 class="page-title">插件目录</h2>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadRegistry">刷新</el-button>
      </div>
    </div>

    <el-alert
      class="safety-alert"
      type="warning"
      show-icon
      :closable="false"
      title="插件是可执行代码。V1 采用可信白名单目录：以下为官方维护插件，安装/升级请在服务器环境手动执行命令后重启服务。请勿安装不可信来源的插件。"
      description="各插件的详细用法（凭据从哪获取、任务说明、配置项、常见问题）见 docs/PLUGINS.md —— 官方插件使用指南。"
    />

    <el-row v-loading="loading" :gutter="16">
      <el-col v-for="entry in entries" :key="entry.plugin_id" :span="12" :xs="24">
        <el-card shadow="never" class="plugin-card">
          <template #header>
            <div class="card-header">
              <span class="plugin-name">{{ entry.name }}</span>
              <div class="card-tags">
                <el-tag v-if="entry.trusted" type="success" size="small">官方信任</el-tag>
                <el-tag :type="versionTagType(entry)" size="small">
                  {{ versionTagText(entry) }}
                </el-tag>
              </div>
            </div>
          </template>

          <p class="plugin-desc">{{ entry.description }}</p>

          <div class="capability-row">
            <el-tag
              v-for="cap in entry.capabilities"
              :key="cap"
              size="small"
              type="info"
              class="cap-tag"
            >
              {{ cap }}
            </el-tag>
            <el-tag v-if="entry.requires_browser" size="small" type="warning">
              需浏览器 worker
            </el-tag>
          </div>

          <div class="install-row">
            <el-input :model-value="entry.install" readonly>
              <template #append>
                <el-button @click="copyInstall(entry.install)">复制</el-button>
              </template>
            </el-input>
          </div>

          <div class="meta-row">
            <el-link :href="entry.homepage" target="_blank" type="primary">查看源码</el-link>
            <span class="package-name">{{ entry.package }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && entries.length === 0" description="目录为空（registry.json 缺失或格式异常）" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { listRegistry } from "../api";
import { extractErrorMessage } from "../api/client";
import type { RegistryEntry } from "../api/types";

// ---------------------------------------------------------------------------
// List state
// ---------------------------------------------------------------------------

const loading = ref(false);
const entries = ref<RegistryEntry[]>([]);

async function loadRegistry(): Promise<void> {
  loading.value = true;
  try {
    entries.value = await listRegistry();
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "加载插件目录失败"));
  } finally {
    loading.value = false;
  }
}

function versionTagText(entry: RegistryEntry): string {
  if (entry.upgradable) {
    return `可升级 → v${entry.version}`;
  }
  if (entry.installed) {
    return `已安装 v${entry.installed_version ?? entry.version}`;
  }
  return "未安装";
}

function versionTagType(entry: RegistryEntry): "success" | "warning" | "info" {
  if (entry.upgradable) {
    return "warning";
  }
  if (entry.installed) {
    return "success";
  }
  return "info";
}

// ---------------------------------------------------------------------------
// Copy install command（与 Agents.vue 相同的剪贴板兜底策略）
// ---------------------------------------------------------------------------

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

async function copyInstall(command: string): Promise<void> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(command);
      ElMessage.success("安装命令已复制到剪贴板");
    } else if (legacyCopy(command)) {
      ElMessage.success("安装命令已复制到剪贴板");
    } else {
      ElMessage.error("复制失败，请手动选择命令复制");
    }
  } catch {
    if (legacyCopy(command)) {
      ElMessage.success("安装命令已复制到剪贴板");
    } else {
      ElMessage.error("复制失败，请手动选择命令复制");
    }
  }
}

onMounted(loadRegistry);
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

.safety-alert {
  margin-bottom: 16px;
}

.plugin-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.plugin-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plugin-desc {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.capability-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.cap-tag {
  font-family: var(--el-font-family, monospace);
}

.install-row {
  margin-bottom: 12px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.package-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
