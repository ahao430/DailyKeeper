/**
 * Shared Chinese label maps for execution statuses and resource types.
 * Keys mirror the backend enums (app/models.py, task engine outcomes).
 */

export type TagType = "primary" | "success" | "warning" | "info" | "danger";

/** Execution status → 中文标签。 */
export const STATUS_LABELS: Record<string, string> = {
  PENDING: "待执行",
  RUNNING: "执行中",
  SUCCESS: "成功",
  FAILED: "失败",
  SKIPPED: "已跳过",
  INTERRUPTED: "已中断",
  AUTH_EXPIRED: "登录失效",
  NEEDS_ACTION: "需人工处理",
  RATE_LIMITED: "触发限流",
};

/** Execution status → el-tag type。 */
export const STATUS_TAG_TYPES: Record<string, TagType> = {
  PENDING: "primary",
  RUNNING: "primary",
  SUCCESS: "success",
  FAILED: "danger",
  SKIPPED: "info",
  INTERRUPTED: "info",
  AUTH_EXPIRED: "warning",
  NEEDS_ACTION: "warning",
  RATE_LIMITED: "warning",
};

/** Resource snapshot type → 中文标签。 */
export const RESOURCE_LABELS: Record<string, string> = {
  balance: "余额",
  points: "积分",
  quota: "可用额度",
  usage: "用量",
  bonus: "魔力",
  upload: "上传量",
  download: "下载量",
  share_rate: "分享率",
};

/** Fallback-friendly label lookup. */
export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function statusTagType(status: string): TagType {
  return STATUS_TAG_TYPES[status] ?? "info";
}

export function resourceLabel(type: string): string {
  return RESOURCE_LABELS[type] ?? type;
}
