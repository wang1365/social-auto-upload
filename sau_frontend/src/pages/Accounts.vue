<script setup lang="ts">
import { computed, ref } from "vue";
import { Plus, Search, Refresh, User } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, post, type Account } from "../api";
import {
  accountLogin,
  act,
  confirm,
  drawerTask,
  isActive,
  platformLetters,
  platformNames,
  refresh,
  state,
} from "../state";
const query = ref(""),
  platform = ref(0),
  dialog = ref(false),
  busy = ref(false);
const name = ref(""),
  newPlatform = ref(3);
const cookieInput = ref<HTMLInputElement>();
const importTarget = ref<Account | null>(null);
const visible = computed(() =>
  state.accounts.filter(
    (a) =>
      (!platform.value || a.type === platform.value) &&
      a.userName.toLowerCase().includes(query.value.toLowerCase()),
  ),
);
const valid = computed(
  () => state.accounts.filter((a) => a.status === 1).length,
);
const busyAccount = (id: number) =>
  state.tasks.some((t) => t.account_id === id && isActive(t));
async function create() {
  if (!name.value.trim()) {
    ElMessage.warning("请输入账号名称");
    return;
  }
  busy.value = true;
  await act(async () => {
    const account = await post<Account>("/accounts", {
      platform: newPlatform.value,
      name: name.value.trim(),
    });
    dialog.value = false;
    name.value = "";
    await refresh();
    await accountLogin(account);
  });
  busy.value = false;
}
async function check(account: Account) {
  await act(async () => {
    const result = await post<{ id: string }>(`/accounts/${account.id}/check`);
    drawerTask.value = result.id;
    await refresh();
  });
}
async function rename(account: Account) {
  const result = await ElMessageBox.prompt(
    "为账号设置容易识别的名称",
    "修改账号名称",
    {
      inputValue: account.userName,
      inputValidator: (value) => !!value?.trim() || "请输入账号名称",
      confirmButtonText: "保存",
      cancelButtonText: "取消",
    },
  ).catch(() => null);
  if (result)
    await act(async () => {
      await api(`/accounts/${account.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: result.value, platform: account.type }),
      });
      await refresh();
    });
}
async function remove(account: Account) {
  if (
    await confirm(
      `删除“${account.userName}”及其本机登录凭据？平台上的账号和内容不会被删除。`,
      "删除账号",
    )
  )
    await act(async () => {
      await api(`/accounts/${account.id}`, { method: "DELETE" });
      await refresh();
    });
}
async function command(value: string, account: Account) {
  if (value === "rename") return rename(account);
  if (value === "delete") return remove(account);
  if (value === "headed") return accountLogin(account, true);
  if (value === "import") {
    importTarget.value = account;
    cookieInput.value?.click();
    return;
  }
  await act(async () => {
    const data = await api<Record<string, unknown>>(
      `/accounts/${account.id}/cookie`,
    );
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `account-${account.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  });
}
async function importCookie(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file && importTarget.value)
    await act(async () => {
      const form = new FormData();
      form.append("file", file);
      const result = await api<{ id: string }>(
        `/accounts/${importTarget.value!.id}/cookie`,
        { method: "POST", body: form },
      );
      drawerTask.value = result.id;
      await refresh();
    });
  if (cookieInput.value) cookieInput.value.value = "";
}
</script>

<template>
  <div class="page-heading">
    <div>
      <div class="eyebrow">账号管理</div>
      <h1>连接您的创作账号</h1>
      <p>一次登录，随时选择账号发布。登录凭据仅保存在本机。</p>
    </div>
    <el-button type="primary" :icon="Plus" @click="dialog = true"
      >添加账号</el-button
    >
  </div>
  <div class="account-stats">
    <span
      ><strong>{{ state.accounts.length }}</strong> 个账号</span
    ><span><i class="status-dot success"></i>{{ valid }} 个登录有效</span
    ><span
      ><i class="status-dot warning"></i
      >{{ state.accounts.length - valid }} 个需要登录</span
    >
  </div>
  <section class="panel">
    <div class="filter-bar">
      <el-input
        v-model="query"
        :prefix-icon="Search"
        placeholder="搜索账号名称"
        clearable
        class="search-field"
      /><el-select v-model="platform" style="width: 150px"
        ><el-option label="全部平台" :value="0" /><el-option
          v-for="(label, id) in platformNames"
          :key="id"
          :label="label"
          :value="Number(id)"
      /></el-select>
    </div>
    <el-table :data="visible" row-key="id"
      ><el-table-column label="账号名称" min-width="240"
        ><template #default="{ row }"
          ><div class="account-cell">
            <span class="platform-avatar" :class="'platform-' + row.type">{{
              platformLetters[row.type]
            }}</span>
            <div>
              <strong>{{ row.userName }}</strong>
              <div class="muted small">{{ platformNames[row.type] }}</div>
            </div>
          </div></template
        ></el-table-column
      ><el-table-column label="登录状态" min-width="180"
        ><template #default="{ row }"
          ><span
            class="status-pill"
            :class="row.status === 1 ? 'succeeded' : 'interrupted'"
            ><i></i>{{ row.status === 1 ? "登录有效" : "需要登录" }}</span
          ><span v-if="busyAccount(row.id)" class="muted small account-tasking"
            >任务处理中</span
          ></template
        ></el-table-column
      ><el-table-column label="操作" width="270" fixed="right"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            :disabled="busyAccount(row.id)"
            @click="accountLogin(row)"
            >{{ row.status === 1 ? "重新登录" : "扫码登录" }}</el-button
          ><el-button link :disabled="busyAccount(row.id)" @click="check(row)"
            >检查状态</el-button
          ><el-dropdown
            trigger="click"
            @command="(value: string) => command(value, row)"
            ><el-button link>更多</el-button
            ><template #dropdown
              ><el-dropdown-menu
                ><el-dropdown-item command="rename">修改名称</el-dropdown-item
                ><el-dropdown-item
                  command="headed"
                  :disabled="busyAccount(row.id)"
                  >打开浏览器登录</el-dropdown-item
                ><el-dropdown-item
                  command="import"
                  :disabled="busyAccount(row.id)"
                  >导入登录凭据</el-dropdown-item
                ><el-dropdown-item command="export"
                  >导出登录凭据</el-dropdown-item
                ><el-dropdown-item
                  command="delete"
                  :disabled="busyAccount(row.id)"
                  divided
                  >删除账号</el-dropdown-item
                ></el-dropdown-menu
              ></template
            ></el-dropdown
          ></template
        ></el-table-column
      ><template #empty
        ><el-empty description="还没有账号，添加一个开始发布吧" :image-size="80"
          ><el-button type="primary" @click="dialog = true"
            >添加第一个账号</el-button
          ></el-empty
        ></template
      ></el-table
    >
  </section>
  <input
    ref="cookieInput"
    type="file"
    accept=".json"
    hidden
    @change="importCookie"
  />
  <el-dialog v-model="dialog" title="添加创作账号" width="500px"
    ><el-form label-position="top" @submit.prevent="create"
      ><el-form-item label="选择平台"
        ><div class="platform-choices">
          <button
            v-for="(label, id) in platformNames"
            :key="id"
            type="button"
            :class="{ active: newPlatform === Number(id) }"
            @click="newPlatform = Number(id)"
          >
            <span class="platform-avatar" :class="'platform-' + id">{{
              platformLetters[Number(id)]
            }}</span>{{ label }}
          </button>
        </div></el-form-item
      ><el-form-item label="账号名称" required
        ><el-input
          v-model="name"
          maxlength="80"
          placeholder="例如：品牌主账号、我的生活号"
          @keyup.enter="create"
      /></el-form-item>
      <div class="info-box">
        名称用于本机识别。下一步使用对应平台 App 扫码完成登录。
      </div></el-form
    ><template #footer
      ><el-button @click="dialog = false">取消</el-button
      ><el-button type="primary" :loading="busy" @click="create"
        >添加并登录</el-button
      ></template
    ></el-dialog
  >
</template>
