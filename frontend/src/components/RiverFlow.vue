<script setup>
import { ref, useId, onMounted, onBeforeUnmount } from 'vue';
import { animate } from 'animejs';

// Distort only the river channel: the paper, banks and interface stay still.
const id = useId().replace(/:/g, '-');
const maskId = `river-mask-${id}`, filterId = `river-filter-${id}`;
const surface = ref(null), turbulence = ref(null), streams = ref(null);
const texture = `${import.meta.env.BASE_URL}art/page-home-water-v4.png`;
const channel = 'M850 -100 C810 40 1000 155 1230 230 C1400 300 1380 400 1140 540 C930 680 750 780 640 1120';
const flow = { phase: 0 };
let animation, observer, media, inView = true;
function paint() {
  const phase = flow.phase * Math.PI * 2;
  turbulence.value.setAttribute('baseFrequency', `${.012 + .002 * Math.sin(phase)} ${.022 + .003 * Math.cos(phase)}`);
  streams.value.setAttribute('stroke-dashoffset', String(-flow.phase * 240));
}
function sync() {
  if (!animation) return;
  const stopped = !inView || document.hidden || media.matches || document.documentElement.dataset.motion === 'off';
  stopped ? animation.pause() : animation.resume();
}
onMounted(() => {
  media = matchMedia('(prefers-reduced-motion: reduce)');
  paint();
  animation = animate(flow, { phase: [0, 1], duration: 12000, ease: 'linear', loop: true, onUpdate: paint });
  media.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync);
  window.addEventListener('openguard-motion', sync);
  observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; sync(); });
  observer.observe(surface.value);
  sync();
});
onBeforeUnmount(() => {
  animation?.cancel(); observer?.disconnect();
  media?.removeEventListener('change', sync);
  document.removeEventListener('visibilitychange', sync);
  window.removeEventListener('openguard-motion', sync);
});
</script>
<template>
  <svg ref="surface" class="river-flow" viewBox="0 0 1536 1024" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <mask :id="maskId" maskUnits="userSpaceOnUse" x="0" y="0" width="1536" height="1024">
        <path :d="channel" fill="none" stroke="white" stroke-width="210" />
      </mask>
      <filter :id="filterId" x="-3%" y="-3%" width="106%" height="106%" color-interpolation-filters="sRGB">
        <feTurbulence ref="turbulence" type="fractalNoise" baseFrequency=".012 .025" numOctaves="1" seed="7" result="water" />
        <feDisplacementMap in="SourceGraphic" in2="water" scale="14" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </defs>
    <g :mask="`url(#${maskId})`">
      <image :href="texture" width="1536" height="1024" preserveAspectRatio="none" :filter="`url(#${filterId})`" opacity=".8" />
      <g ref="streams" fill="none" stroke-linecap="round" stroke-dasharray="32 208" stroke-dashoffset="0">
        <path :d="channel" stroke="#f2fcff" stroke-width="5" opacity=".65" />
        <path :d="channel" transform="translate(34 0)" stroke="#5aa9d3" stroke-width="3" opacity=".4" />
        <path :d="channel" transform="translate(-45 12)" stroke="#f2fcff" stroke-width="3" opacity=".55" />
      </g>
    </g>
  </svg>
</template>
<style scoped>
.river-flow { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
</style>
