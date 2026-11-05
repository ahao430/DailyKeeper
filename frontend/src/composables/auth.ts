import { computed, ref } from "vue";

/**
 * Global auth state. Token lives in localStorage under "dk_token";
 * the module-scope refs mirror it so router guards and layouts react.
 */
const TOKEN_KEY = "dk_token";

const token = ref<string | null>(readToken());
const username = ref<string>("");

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function useAuth() {
  const isLoggedIn = computed(() => token.value !== null && token.value !== "");

  function setToken(value: string): void {
    token.value = value;
    localStorage.setItem(TOKEN_KEY, value);
  }

  function clearToken(): void {
    token.value = null;
    username.value = "";
    localStorage.removeItem(TOKEN_KEY);
  }

  function setUsername(value: string): void {
    username.value = value;
  }

  return { token, username, isLoggedIn, setToken, clearToken, setUsername };
}
