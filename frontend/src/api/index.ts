/**
 * Typed wrappers for every backend endpoint.
 * Shapes mirror backend/app/api/*.py exactly.
 */
import client from "./client";
import type {
  Account,
  BootstrapResponse,
  ChangePasswordRequest,
  CheckResponse,
  CreateAccountRequest,
  CreatePlatformRequest,
  CreateScheduledTaskRequest,
  Execution,
  ListExecutionsParams,
  ListResourcesParams,
  LoginRequest,
  LoginResponse,
  MeResponse,
  NotificationSettings,
  OkResponse,
  PlatformInstance,
  PluginManifest,
  ResourceSnapshot,
  ResourceSummary,
  RunNowResponse,
  ScheduledTask,
  SystemInfo,
  SystemSettings,
  TestNotificationRequest,
  TestNotificationResponse,
  UpdateAccountRequest,
  UpdatePlatformRequest,
  UpdateScheduledTaskRequest,
} from "./types";

function unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
  return promise.then((response) => response.data);
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function login(payload: LoginRequest): Promise<LoginResponse> {
  return unwrap(client.post<LoginResponse>("/auth/login", payload));
}

export function getBootstrap(): Promise<BootstrapResponse> {
  return unwrap(client.get<BootstrapResponse>("/auth/bootstrap"));
}

export function getMe(): Promise<MeResponse> {
  return unwrap(client.get<MeResponse>("/auth/me"));
}

export function changePassword(payload: ChangePasswordRequest): Promise<OkResponse> {
  return unwrap(client.put<OkResponse>("/auth/password", payload));
}

// ---------------------------------------------------------------------------
// Plugins
// ---------------------------------------------------------------------------

export function listPlugins(): Promise<PluginManifest[]> {
  return unwrap(client.get<PluginManifest[]>("/plugins"));
}

// ---------------------------------------------------------------------------
// Platforms
// ---------------------------------------------------------------------------

export function listPlatforms(): Promise<PlatformInstance[]> {
  return unwrap(client.get<PlatformInstance[]>("/platforms"));
}

export function createPlatform(payload: CreatePlatformRequest): Promise<PlatformInstance> {
  return unwrap(client.post<PlatformInstance>("/platforms", payload));
}

export function getPlatform(instanceId: number): Promise<PlatformInstance> {
  return unwrap(client.get<PlatformInstance>(`/platforms/${instanceId}`));
}

export function updatePlatform(
  instanceId: number,
  payload: UpdatePlatformRequest,
): Promise<PlatformInstance> {
  return unwrap(client.put<PlatformInstance>(`/platforms/${instanceId}`, payload));
}

export function deletePlatform(instanceId: number): Promise<OkResponse> {
  return unwrap(client.delete<OkResponse>(`/platforms/${instanceId}`));
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export function listAccounts(instanceId?: number): Promise<Account[]> {
  return unwrap(
    client.get<Account[]>("/accounts", {
      params: instanceId === undefined ? {} : { instance_id: instanceId },
    }),
  );
}

export function createAccount(payload: CreateAccountRequest): Promise<Account> {
  return unwrap(client.post<Account>("/accounts", payload));
}

export function getAccount(accountId: number): Promise<Account> {
  return unwrap(client.get<Account>(`/accounts/${accountId}`));
}

export function updateAccount(accountId: number, payload: UpdateAccountRequest): Promise<Account> {
  return unwrap(client.put<Account>(`/accounts/${accountId}`, payload));
}

export function deleteAccount(accountId: number): Promise<OkResponse> {
  return unwrap(client.delete<OkResponse>(`/accounts/${accountId}`));
}

export function checkAccount(accountId: number): Promise<CheckResponse> {
  return unwrap(client.post<CheckResponse>(`/accounts/${accountId}/check`));
}

// ---------------------------------------------------------------------------
// Scheduled tasks
// ---------------------------------------------------------------------------

export function listScheduledTasks(accountId?: number): Promise<ScheduledTask[]> {
  return unwrap(
    client.get<ScheduledTask[]>("/scheduled-tasks", {
      params: accountId === undefined ? {} : { account_id: accountId },
    }),
  );
}

export function createScheduledTask(payload: CreateScheduledTaskRequest): Promise<ScheduledTask> {
  return unwrap(client.post<ScheduledTask>("/scheduled-tasks", payload));
}

export function updateScheduledTask(
  taskId: number,
  payload: UpdateScheduledTaskRequest,
): Promise<ScheduledTask> {
  return unwrap(client.put<ScheduledTask>(`/scheduled-tasks/${taskId}`, payload));
}

export function deleteScheduledTask(taskId: number): Promise<OkResponse> {
  return unwrap(client.delete<OkResponse>(`/scheduled-tasks/${taskId}`));
}

export function runScheduledTaskNow(taskId: number): Promise<RunNowResponse> {
  return unwrap(client.post<RunNowResponse>(`/scheduled-tasks/${taskId}/run-now`));
}

// ---------------------------------------------------------------------------
// Executions
// ---------------------------------------------------------------------------

export function listExecutions(params: ListExecutionsParams = {}): Promise<Execution[]> {
  return unwrap(client.get<Execution[]>("/executions", { params }));
}

export function getExecution(executionId: number): Promise<Execution> {
  return unwrap(client.get<Execution>(`/executions/${executionId}`));
}

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

export function listResources(params: ListResourcesParams = {}): Promise<ResourceSnapshot[]> {
  return unwrap(client.get<ResourceSnapshot[]>("/resources", { params }));
}

export function getResourceSummary(): Promise<ResourceSummary[]> {
  return unwrap(client.get<ResourceSummary[]>("/resources/summary"));
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export function getSystemInfo(): Promise<SystemInfo> {
  return unwrap(client.get<SystemInfo>("/system/info"));
}

export function getSystemSettings(): Promise<SystemSettings> {
  return unwrap(client.get<SystemSettings>("/system/settings"));
}

export function updateNotificationSettings(payload: NotificationSettings): Promise<OkResponse> {
  return unwrap(client.put<OkResponse>("/system/settings/notifications", payload));
}

export function testNotification(payload: TestNotificationRequest): Promise<TestNotificationResponse> {
  return unwrap(client.post<TestNotificationResponse>("/system/notifications/test", payload));
}
