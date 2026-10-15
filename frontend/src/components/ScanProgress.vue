<script setup>
import Icon from './Icon.vue';
import CrystalCat from './WatercolorCat.vue';
defineProps({phase: String, selectedName: String, progress: Number, seconds: Number, mode: String});
</script>
<template>
  <section class="scan-progress panel" aria-live="polite">
    <span class="eyebrow">扫描进行中</span><CrystalCat mood="analyzing" small />
    <h1>{{ phase === 'uploading' ? '正在上传你的项目' : '正在进行静态安全审查' }}</h1>
    <p class="muted">{{ selectedName }}</p>
    <div v-if="phase === 'uploading'" class="upload-meter"><div :style="{width: progress + '%'}"></div></div>
    <p v-if="phase === 'uploading'">上传进度 {{ progress }}%</p>
    <div v-else class="indeterminate"><span></span></div>
    <div class="process-chips"><span><Icon name="KeyRound" :size="17" />Secret 检测</span><Icon name="ChevronRight" :size="14" /><span><Icon name="FileCheck2" :size="17" />许可证分析</span><Icon name="ChevronRight" :size="14" /><span><Icon name="Bot" :size="17" />Agent 安全</span></div>
    <p class="muted small-text">已等待 {{ seconds }} 秒 · 完成后自动打开结果</p>
    <p class="progress-note">以上为扫描流程说明。当前服务不提供逐阶段进度，结果以实际扫描返回为准。</p>
    <RouterLink :to="{path: '/history', query: {mode}}" class="text-button">离开后可在扫描历史查看结果</RouterLink>
  </section>
</template>
