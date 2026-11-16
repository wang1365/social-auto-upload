import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "工作台",
      component: () => import("./pages/Dashboard.vue"),
    },
    {
      path: "/publish",
      name: "发布中心",
      component: () => import("./pages/Publish.vue"),
    },
    {
      path: "/materials",
      name: "素材库",
      component: () => import("./pages/Materials.vue"),
    },
    {
      path: "/youtube",
      name: "YouTube 浏览",
      component: () => import("./pages/YouTube.vue"),
    },
    {
      path: "/downloads",
      name: "下载中心",
      component: () => import("./pages/Downloads.vue"),
    },
    {
      path: "/accounts",
      name: "账号管理",
      component: () => import("./pages/Accounts.vue"),
    },
    {
      path: "/settings",
      name: "设置",
      component: () => import("./pages/Settings.vue"),
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});
