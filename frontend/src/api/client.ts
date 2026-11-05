import axios from "axios";

/**
 * Shared axios client. Base URL is "/api" and Vite proxies it to the backend.
 * The admin token is kept in localStorage under "dk_token"; on 401 the token
 * is dropped and the browser is sent back to the login page.
 */
export const TOKEN_KEY = "dk_token";

const client = axios.create({
  baseURL: "/api",
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      // 登录页自身的 401（密码错误）不重定向，避免刷新打断错误提示
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

/** Extract the human-readable message from a backend error response. */
export function extractErrorMessage(error: unknown, fallback = "请求失败，请稍后重试"): string {
  if (axios.isAxiosError(error)) {
    const data: unknown = error.response?.data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) {
        return detail;
      }
      if (detail !== undefined && detail !== null) {
        return JSON.stringify(detail);
      }
    }
    if (error.message) {
      return error.message;
    }
  }
  return fallback;
}

export default client;
