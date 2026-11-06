import { createRouter, createWebHistory } from "vue-router";
import { TOKEN_KEY } from "../api/client";
import MainLayout from "../layouts/MainLayout.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("../views/Login.vue"),
      meta: { title: "登录" },
    },
    {
      path: "/",
      component: MainLayout,
      children: [
        {
          path: "",
          name: "dashboard",
          component: () => import("../views/Dashboard.vue"),
          meta: { title: "总览" },
        },
        {
          path: "platforms",
          name: "platforms",
          component: () => import("../views/Platforms.vue"),
          meta: { title: "平台与账号" },
        },
        {
          path: "registry",
          name: "registry",
          component: () => import("../views/Registry.vue"),
          meta: { title: "插件目录" },
        },
        {
          path: "tasks",
          name: "tasks",
          component: () => import("../views/Tasks.vue"),
          meta: { title: "任务中心" },
        },
        {
          path: "executions",
          name: "executions",
          component: () => import("../views/Executions.vue"),
          meta: { title: "执行日志" },
        },
        {
          path: "resources",
          name: "resources",
          component: () => import("../views/Resources.vue"),
          meta: { title: "资源看板" },
        },
        {
          path: "agents",
          name: "agents",
          component: () => import("../views/Agents.vue"),
          meta: { title: "执行端管理" },
        },
        {
          path: "settings",
          name: "settings",
          component: () => import("../views/Settings.vue"),
          meta: { title: "系统设置" },
        },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (to.path !== "/login" && !token) {
    return { path: "/login", query: to.fullPath === "/" ? {} : { redirect: to.fullPath } };
  }
  if (to.path === "/login" && token) {
    return { path: "/" };
  }
  return true;
});

router.afterEach((to) => {
  const title = to.meta.title as string | undefined;
  document.title = title ? `${title} · DailyKeeper 每日管家` : "DailyKeeper 每日管家";
});

export default router;
