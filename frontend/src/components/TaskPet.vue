<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import WatercolorCat from './WatercolorCat.vue';
import { assistant, taskHint } from '../assistant';
import { state } from '../state';
import { coverageSummary } from '../domain';
const route = useRoute(), collapsed = ref(true), quiet = ref(true);
const docked = computed(() => !['/', '/entry'].includes(route.path));
const mobile = matchMedia('(max-width: 760px)');
function fitScreen() { if (mobile.matches) { collapsed.value = true; quiet.value = true; } }
onMounted(() => mobile.addEventListener('change', fitScreen));
onBeforeUnmount(() => mobile.removeEventListener('change', fitScreen));
const hint = computed(() => taskHint({ ...assistant, path: route.path, section: route.params.section, loading: state.scanLoading && !!route.params.id, scanError: route.params.id ? state.scanError : '', scan: state.scan, complete: state.scan ? coverageSummary(state.scan).complete : false }));
watch(() => hint.value.title, () => { if (!quiet.value) collapsed.value = false; });
</script>
<template>
  <aside class="task-pet" :class="{docked}" data-testid="task-pet" :data-state="hint.mood" aria-label="小护任务助手">
    <div v-if="!collapsed" class="pet-message" aria-live="polite">
      <div class="pet-message-head"><b>{{ hint.title }}</b><button @click="collapsed = true" aria-label="收起小护提示">×</button></div>
      <p>{{ hint.text }}</p>
      <div class="pet-tools"><button @click="quiet = !quiet" :aria-pressed="quiet">{{ quiet ? '恢复自动提示' : '暂停自动提示' }}</button><RouterLink to="/entry">使用入口</RouterLink></div>
    </div>
    <WatercolorCat :mood="hint.mood" @pet="collapsed = !collapsed" />
    <span class="pet-name">小护 · {{ collapsed ? '点击看提示' : '陪你看清风险' }}</span>
  </aside>
</template>
