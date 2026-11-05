/**
 * TypeScript mirrors of the backend request/response shapes
 * (see backend/app/api/*.py and sdk/dailykeeper_sdk/base.py).
 */

/** One dynamic form field declared by a plugin (dailykeeper_sdk FieldDef). */
export interface FieldDef {
  name: string;
  label: string;
  type: "string" | "secret" | "number" | "boolean" | "select";
  required: boolean;
  default: unknown;
  options: unknown[] | null;
  help: string;
  placeholder: string;
}

/** One task a plugin can execute (dailykeeper_sdk TaskDefinition). */
export interface TaskDefinition {
  name: string;
  description: string;
  description_en: string;
  requires_browser: boolean;
  default_time: string;
  produces_resources: boolean;
  idempotent: boolean;
  allow_concurrent: boolean;
}

/** GET /api/plugins item (manifest plus "enabled"). */
export interface PluginManifest {
  plugin_id: string;
  plugin_name: string;
  version: string;
  description: string;
  auth_types: string[];
  config_schema: FieldDef[];
  account_schema: FieldDef[];
  task_definitions: TaskDefinition[];
  requires_browser_any: boolean;
  enabled: boolean;
}

/** GET/POST/PUT /api/platforms item. */
export interface PlatformInstance {
  id: number;
  platform_id: string;
  platform_name: string;
  name: string;
  base_url: string;
  config: Record<string, unknown>;
  timezone: string;
  description: string;
  enabled: boolean;
  account_count: number;
}

export type AccountStatus = "ACTIVE" | "AUTH_EXPIRED" | "DISABLED" | (string & {});

/** GET/POST/PUT /api/accounts item. */
export interface Account {
  id: number;
  instance_id: number;
  instance_name: string;
  platform_id: string;
  name: string;
  display_name: string;
  status: AccountStatus;
  enabled: boolean;
  notes: string;
  config: Record<string, unknown>;
  last_task_at: string | null;
  last_checkin_date: string | null;
  has_credential: boolean;
  credential_kind: string | null;
}

/** GET/POST /api/scheduled-tasks item. */
export interface ScheduledTask {
  id: number;
  account_id: number;
  account_name: string;
  platform_id: string;
  instance_name: string;
  timezone: string;
  task_name: string;
  time_of_day: string;
  interval_days: number;
  params: Record<string, unknown>;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
}

/** Structured task result embedded in executions and check responses. */
export interface ExecutionResult {
  success: boolean;
  status: string;
  message: string;
  data: unknown;
  metrics: Record<string, unknown> | null;
}

/** GET /api/executions item. */
export interface Execution {
  id: number;
  account_id: number;
  account_name: string;
  platform_id: string;
  instance_name: string;
  task_name: string;
  business_date: string;
  status: string;
  retries: number;
  worker_id: string | null;
  due_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  result: ExecutionResult | null;
}

/** GET /api/resources item. */
export interface ResourceSnapshot {
  id: number;
  account_id: number;
  account_name: string;
  resource_type: string;
  value: number | null;
  text_value: string | null;
  unit: string | null;
  observed_at: string;
  source: string;
}

/** GET /api/resources/summary item. */
export interface ResourceSummary {
  account_id: number;
  account_name: string;
  platform_id: string;
  instance_name: string;
  resource_type: string;
  value: number | null;
  text_value: string | null;
  unit: string | null;
  observed_at: string;
}

/** scheduler_heartbeat inside GET /api/system/info. */
export interface SchedulerHeartbeat {
  at: string;
  fresh: boolean;
}

/** GET /api/system/info. */
export interface SystemInfo {
  app_name: string;
  version: string;
  env: string;
  database: string;
  timezone: string;
  plugins: number;
  instances: number;
  accounts: number;
  scheduled_tasks: number;
  executions_today: number;
  executions_today_success: number;
  notifications_enabled: boolean;
  scheduler_heartbeat: SchedulerHeartbeat | null;
}

/** One notification channel spec ({type, name, config, enabled?}). */
export interface NotificationChannelSpec {
  type: string;
  name: string;
  config: Record<string, unknown>;
  /** Dispatch skips disabled channels (backend filters on spec.get("enabled", True)). */
  enabled?: boolean;
}

/** Notification config stored under SystemSetting key "notifications". */
export interface NotificationSettings {
  enabled: boolean;
  channels: NotificationChannelSpec[];
  events: Record<string, { enabled: boolean }>;
  thresholds: Record<string, unknown>;
}

/** GET /api/system/settings. */
export interface SystemSettings {
  notifications: NotificationSettings;
  general: {
    timezone: string;
    env: string;
    version: string;
  };
}

/** POST /api/auth/login. */
export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
}

/** GET /api/auth/bootstrap. */
export interface BootstrapResponse {
  default_credentials: boolean;
}

/** GET /api/auth/me. */
export interface MeResponse {
  username: string;
}

/** Generic {ok: true} responses (password change, settings PUT, deletes). */
export interface OkResponse {
  ok: boolean;
}

/** POST /api/accounts/{id}/check. */
export interface CheckResponse {
  ok: boolean;
  status: string;
  message: string;
  data: unknown;
  metrics: Record<string, unknown> | null;
  execution_id: number;
}

/** POST /api/scheduled-tasks/{id}/run-now. */
export interface RunNowResponse {
  created: boolean;
  execution_id: number | null;
  message: string;
}

/** POST /api/system/notifications/test. */
export interface TestNotificationResponse {
  ok: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Request payloads
// ---------------------------------------------------------------------------

export interface LoginRequest {
  username: string;
  password: string;
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

export interface CreatePlatformRequest {
  platform_id: string;
  name: string;
  base_url?: string;
  config?: Record<string, unknown>;
  timezone?: string;
  description?: string;
  enabled?: boolean;
}

export interface UpdatePlatformRequest {
  name?: string;
  base_url?: string;
  config?: Record<string, unknown>;
  timezone?: string;
  description?: string;
  enabled?: boolean;
}

export interface CredentialInput {
  kind: string;
  data: Record<string, unknown>;
}

export interface CreateAccountRequest {
  instance_id: number;
  name: string;
  display_name?: string;
  config?: Record<string, unknown>;
  credential: CredentialInput;
}

export interface CredentialUpdate {
  kind?: string;
  data?: Record<string, unknown>;
}

export interface UpdateAccountRequest {
  display_name?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
  notes?: string;
  credential?: CredentialUpdate;
}

export interface CreateScheduledTaskRequest {
  account_id: number;
  task_name: string;
  time_of_day?: string;
  interval_days?: number;
  params?: Record<string, unknown>;
  enabled?: boolean;
}

export interface UpdateScheduledTaskRequest {
  time_of_day?: string;
  interval_days?: number;
  params?: Record<string, unknown>;
  enabled?: boolean;
}

export interface ListExecutionsParams {
  status?: string;
  account_id?: number;
  task_name?: string;
  limit?: number;
  offset?: number;
}

export interface ListResourcesParams {
  account_id?: number;
  resource_type?: string;
  limit?: number;
}

export interface TestNotificationRequest {
  type: string;
  name: string;
  config: Record<string, unknown>;
}
