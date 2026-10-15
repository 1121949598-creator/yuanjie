<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { animate } from 'animejs';
const boat = ref(null), path = ref(null);
let animation, observer, media, inView = true;
const voyage = { progress: .32 };
function paint() {
  const length = path.value.getTotalLength();
  const point = path.value.getPointAtLength(voyage.progress * length);
  const after = path.value.getPointAtLength(Math.min(length, voyage.progress * length + 4));
  const angle = Math.max(-12, Math.min(12, Math.atan2(after.y - point.y, after.x - point.x) * 180 / Math.PI));
  boat.value.setAttribute('transform', `translate(${point.x} ${point.y}) rotate(${angle})`);
}
function sync() { if (!animation) return; !inView || document.hidden || media.matches || document.documentElement.dataset.motion === 'off' ? animation.pause() : animation.resume(); }
onMounted(() => {
  paint(); media = window.matchMedia('(prefers-reduced-motion: reduce)');
  animation = animate(voyage, { progress: [.05, .95], duration: 26000, ease: 'inOutSine', alternate: true, loop: true, onUpdate: paint });
  media.addEventListener('change', sync); document.addEventListener('visibilitychange', sync);
  window.addEventListener('openguard-motion', sync);
  observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; sync(); });
  observer.observe(boat.value.ownerSVGElement); sync();
});
onBeforeUnmount(() => { animation?.cancel(); observer?.disconnect(); media?.removeEventListener('change',sync); document.removeEventListener('visibilitychange',sync); window.removeEventListener('openguard-motion', sync); });
</script>
<template>
  <div class="river-voyage">
    <svg viewBox="0 0 1536 1024" preserveAspectRatio="none" role="img" aria-label="沿着蓝色河流缓慢航行的小船">
      <path ref="path" d="M1140 540 C1380 400 1400 300 1230 230 C1160 190 1100 185 1010 155" fill="none" stroke="none"/>
      <g ref="boat" data-testid="river-boat">
        <g transform="rotate(12)">
          <path d="M-88 31 Q0 55 88 31" stroke="#78b9d3" stroke-width="5" fill="none" opacity=".6"/>
          <path d="M-76 13 Q-23 27 70 10 L52 29 Q-17 44-64 25Z" fill="#203541"/>
          <path d="M-62 16 Q0 26 55 14" fill="none" stroke="#faf9ee" stroke-width="3"/>
          <path d="M-20 17 L-24-58 M15 15 L11-39" stroke="#223843" stroke-width="2.4" stroke-linecap="round"/>
          <path d="M-25-52 L-56-5 L-24-9Z" fill="#fcf9e9" stroke="#526572" stroke-width="1"/>
          <path d="M-19-49 L2-12 L-19-10Z" fill="#e17056"/>
          <path d="M11-33 L31-9 L12-8Z" fill="#a5d6e6"/>
          <circle cx="-44" cy="8" r="9" fill="#e2624f"/><circle cx="-12" cy="10" r="6" fill="#eab84c"/><circle cx="16" cy="8" r="8" fill="#4b9e7e"/><circle cx="39" cy="4" r="9" fill="#347bb5"/>
          <path d="M-23-58l11 3-10 3Z" fill="#eab84c"/>
        </g>
      </g>
    </svg>
  </div>
</template>
<style scoped>
.river-voyage{position:absolute;inset:0;pointer-events:none}
svg{display:block;width:100%;height:100%;overflow:visible}
</style>
