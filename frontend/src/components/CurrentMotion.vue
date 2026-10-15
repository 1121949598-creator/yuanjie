<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { animate } from 'animejs';
const layer = ref(null);
let movement, media;
function sync() { if (!movement) return; document.hidden || media.matches || document.documentElement.dataset.motion === 'off' ? movement.pause() : movement.resume(); }
onMounted(() => {
  media = matchMedia('(prefers-reduced-motion: reduce)');
  movement = animate(layer.value.querySelectorAll('.current-speck'), { translateY: [-12, 16], translateX: [-5, 12], opacity: [.15, .5], duration: (_, i) => 5000 + i * 530, delay: (_, i) => i * 210, alternate: true, loop: true, ease: 'inOutSine' });
  document.addEventListener('visibilitychange', sync); window.addEventListener('openguard-motion', sync); media.addEventListener('change', sync); sync();
});
onBeforeUnmount(() => { movement?.cancel(); document.removeEventListener('visibilitychange', sync); window.removeEventListener('openguard-motion', sync); media?.removeEventListener('change', sync); });
</script>
<template>
  <div ref="layer" class="current-motion" aria-hidden="true">
    <svg viewBox="0 0 1440 1000" preserveAspectRatio="xMidYMid slice"><g class="current-streams"><path d="M960 -80C1320 200 750 300 1060 550S1380 820 1120 1100"/><path d="M1030 -80C1390 200 820 300 1130 550S1450 820 1190 1100"/><path d="M1100 -80C1460 200 890 300 1200 550S1520 820 1260 1100"/></g><circle v-for="i in 18" :key="i" class="current-speck" :cx="880 + ((i * 79) % 430)" :cy="(i * 137) % 980" :r="2 + i % 4" :fill="['#d7a342','#64a592','#709fc4','#d98b75'][i % 4]"/></svg>
  </div>
</template>
