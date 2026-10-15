<script setup>
defineProps({ compact: Boolean, turnDuration: { type: Number, default: 24 } });
</script>
<template>
  <RouterLink class="brand" to="/" aria-label="源界 首页"
    :style="{ '--brand-turn-duration': `${turnDuration}s` }"
    ><span class="brand-symbol" aria-hidden="true"
      ><svg viewBox="0 0 48 48" width="43" height="43" aria-hidden="true">
        <path class="brand-orbit" d="M37 10A19 19 0 1 0 23 43" fill="none" stroke="#247dcb" stroke-width="7" stroke-linecap="round" />
        <path d="M12 10A19 19 0 0 1 33 6" fill="none" stroke="#83c8e4" stroke-width="4" stroke-linecap="round" />
        <circle cx="36" cy="37" r="3" fill="#efb93e" />
        <circle cx="42" cy="28" r="2.5" fill="#e16c50" />
        <circle cx="29" cy="44" r="2" fill="#5bb4aa" />
      </svg></span
    ><span><b>源<span class="brand-blue">界</span></b
      ><small v-if="!compact">AI 开源项目安全审查</small></span
    ></RouterLink
  >
</template>
<style scoped>
.brand-orbit {
  transform-box: fill-box;
  transform-origin: center;
  animation: brand-orbit var(--brand-turn-duration, 24s) linear infinite;
}
@keyframes brand-orbit {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .brand-orbit { animation-duration: 0.01ms; animation-iteration-count: 1; }
}
</style>
