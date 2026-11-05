<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-brand">
        <h1 class="login-title">DailyKeeper 每日管家</h1>
        <p class="login-subtitle">管理员登录</p>
      </div>

      <el-alert
        v-if="showDefaultWarning"
        class="login-alert"
        type="warning"
        show-icon
        :closable="false"
        title="正在使用默认密码 admin/admin123，请尽快在系统设置中修改"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @keyup.enter="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :prefix-icon="User" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :prefix-icon="Lock"
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            class="login-button"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { Lock, User } from "@element-plus/icons-vue";
import { getBootstrap, getMe, login as apiLogin } from "../api";
import { extractErrorMessage } from "../api/client";
import { useAuth } from "../composables/auth";

const route = useRoute();
const router = useRouter();
const { setToken, setUsername } = useAuth();

const formRef = ref<FormInstance>();
const loading = ref(false);
const showDefaultWarning = ref(false);

const form = reactive({
  username: "",
  password: "",
});

const rules: FormRules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

onMounted(async () => {
  try {
    const bootstrap = await getBootstrap();
    showDefaultWarning.value = bootstrap.default_credentials;
  } catch {
    // 后端暂不可达时不阻塞登录页
  }
});

async function handleLogin(): Promise<void> {
  // el-form validate() resolves with undefined; map it to an explicit boolean
  const valid = await formRef.value
    ?.validate()
    .then(() => true)
    .catch(() => false);
  if (!valid) {
    return;
  }
  loading.value = true;
  try {
    const data = await apiLogin({
      username: form.username.trim(),
      password: form.password,
    });
    setToken(data.access_token);
    try {
      const me = await getMe();
      setUsername(me.username);
    } catch {
      setUsername(form.username.trim());
    }
    ElMessage.success("登录成功");
    const redirect = route.query.redirect;
    router.push(typeof redirect === "string" && redirect ? redirect : "/");
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, "登录失败，请稍后重试"));
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #e8f1fd 0%, #f5f7fa 100%);
}

.login-card {
  width: 400px;
  padding: 8px 12px 4px;
}

.login-brand {
  text-align: center;
  margin-bottom: 20px;
}

.login-title {
  margin: 0 0 6px;
  font-size: 22px;
  color: var(--el-text-color-primary);
}

.login-subtitle {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.login-alert {
  margin-bottom: 16px;
}

.login-button {
  width: 100%;
}
</style>
