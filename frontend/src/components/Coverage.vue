<script setup>
import { computed } from "vue";
import Icon from "./Icon.vue";
import { coverageSummary, moduleNames, statusLabels } from "../domain";
const props = defineProps({ scan: Object });
const coverage = computed(() => coverageSummary(props.scan));
</script>
<template>
  <div class="coverage-strip" :class="{ incomplete: !coverage.complete }">
    <Icon :name="coverage.complete ? 'ShieldCheck' : 'Info'" :size="19" /><span
      ><b>{{ coverage.complete ? "本次适用检查已完成" : "请同时关注检测覆盖" }}</b
      ><span class="coverage-description">{{
        coverage.complete
          ? "静态分析结果仍需结合证据人工复核。"
          : "未启用、不可用或部分完成的模块，不能作为检查通过的依据。"
      }}</span></span
    >
    <div class="coverage-modules">
      <span v-for="(label, key) in coverage.modules" :key="key"
        ><i
          class="status-dot"
          :class="{ offline: coverage.scanners[key]?.status !== 'success' }"
        ></i
        >{{ label
        }}<b>{{
          statusLabels[coverage.scanners[key]?.status] || "未知"
        }}</b></span
      >
    </div>
  </div>
</template>
