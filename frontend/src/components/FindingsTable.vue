<script setup>
import { localize } from "../language";
import Icon from "./Icon.vue";
import Badge from "./Badge.vue";
import { categoryLabels, percent, findingLocation } from "../domain";
defineProps({ items: { default: () => [] }, compact: Boolean });
defineEmits(["select"]);
</script>
<template>
  <div v-if="!items.length" class="empty-state compact">
    <Icon name="ShieldCheck" :size="32" />
    <h3>没有匹配的风险项</h3>
    <p>请结合模块覆盖状态理解结果，或调整筛选条件。</p>
  </div>
  <div v-else class="table-scroll">
    <table class="findings-table">
      <thead>
        <tr>
          <th>风险与定位</th>
          <th>风险等级</th>
          <th v-if="!compact">检测类型</th>
          <th>置信度</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="f in items" :key="f.id">
          <td>
            <button class="finding-title" @click="$emit('select', f)">
              {{ localize(f.title) }}</button
            ><small class="file-location"
              ><Icon name="FileText" :size="12" />{{
                findingLocation(f)?.path || "未记录位置"
              }}<span v-if="findingLocation(f)"
                >:{{ findingLocation(f).start_line }}</span
              ></small
            >
          </td>
          <td><Badge :value="f.severity" /></td>
          <td v-if="!compact">
            <span class="type-label">{{
              categoryLabels[f.category] || f.category
            }}</span>
          </td>
          <td>
            <span class="confidence-cell"
              >{{ percent(f.confidence)
              }}<span class="mini-meter"
                ><i :style="{ width: percent(f.confidence) }"></i></span
            ></span>
          </td>
          <td>
            <button
              class="icon-button"
              @click="$emit('select', f)"
              :aria-label="`查看 ${f.title} 详情`"
            >
              <Icon name="ChevronRight" :size="17" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
