<script setup>
import { ref, computed, onMounted } from "vue";
import Icon from "../components/Icon.vue";
import Badge from "../components/Badge.vue";
import { state, loadHistory } from "../state";
import { formatDate } from "../domain";
import { useRoute } from "vue-router";
import { journeys, journeyKey, historyResultPath } from "../journeys";
const route = useRoute();
const mode = computed(() => journeyKey(route.query.mode));
const journey = computed(() => journeys[mode.value]);
const search = ref(""),
  loading = ref(true);
const items = computed(() =>
  state.history.filter((s) =>
    s.project_name.toLowerCase().includes(search.value.toLowerCase()),
  ),
);
async function refresh() {
  loading.value = true;
  await loadHistory();
  loading.value = false;
}
onMounted(refresh);
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="workspace-label">{{ journey.title }} / 扫描记录</p>
      <h1>之前查过的，都在这里。</h1>
      <p>各入口的历史扫描都保存在这里。按名称找到记录，接着看证据和报告。</p>
    </div>
    <RouterLink class="button primary" :to="{path: '/new', query: {mode}}"
      ><Icon name="Plus" :size="18" />新建扫描</RouterLink
    >
  </div>
  <section class="panel">
    <div class="panel-toolbar">
      <div class="search-field">
        <Icon name="Search" :size="17" /><input
          v-model="search"
          placeholder="搜索项目名称"
          aria-label="搜索扫描历史"
        />
      </div>
      <button class="button quiet" @click="refresh">
        <Icon name="RefreshCw" :size="17" />刷新
      </button>
    </div>
    <div v-if="state.historyError" class="alert error" role="alert">
      {{ state.historyError }}
    </div>
    <div v-else-if="loading" class="empty-state">
      <Icon name="LoaderCircle" class="spin" />
      <p>正在读取扫描记录</p>
    </div>
    <div v-else-if="!items.length" class="empty-state">
      <Icon name="History" :size="42" />
      <h3>{{ search ? "没有匹配的项目" : "还没有扫描记录" }}</h3>
      <p>上传你的第一个项目，或选择一个合成示例。</p>
      <RouterLink class="button secondary" :to="{path: '/new', query: {mode}}">开始第一次扫描</RouterLink>
    </div>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>项目名称</th>
            <th>扫描时间</th>
            <th>发现问题</th>
            <th>扫描状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <div class="project-cell">
                <span class="file-icon"><Icon name="Folder" :size="19" /></span>
                <div>
                  <RouterLink :to="historyResultPath(item, mode)">{{
                    item.project_name
                  }}</RouterLink
                  ><small
                    >{{
                      (item.is_example || /^synthetic-(release|research|secrets|dynamic|mcp)$/.test(item.project_name)) ? "合成示例 · 真实执行" : "上传项目"
                    }}
                    · {{ item.id.slice(0, 8) }}</small
                  >
                </div>
              </div>
            </td>
            <td class="muted">{{ formatDate(item.created_at) }}</td>
            <td>
              <b>{{ item.summary.total_findings }}</b>
              <span class="muted">项</span>
            </td>
            <td><Badge :value="item.status" kind="status" /></td>
            <td>
              <RouterLink class="text-button" :to="historyResultPath(item, mode)"
                >查看结果 <Icon name="ArrowUpRight" :size="15"
              /></RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="table-footer">
      <span>最近 {{ state.history.length }} 条记录（最多显示 100 条）</span
      ><span>数据保存在本地，重启后可继续查看</span>
    </div>
  </section>
</template>
