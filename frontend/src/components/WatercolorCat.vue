<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue';
const props = defineProps({ mood: {type: String, default: 'idle'}, small: Boolean });
const emit = defineEmits(['pet']);
const petting = ref(false), sleeping = ref(false);
const poses = ['idle', 'thinking', 'analyzing', 'success', 'guide', 'warning', 'celebrate', 'sleep'];
const labels = ['默认站立', '思考中', '正在分析', '成功完成', '引导提示', '警告提醒', '庆祝鼓励', '躺平休息'];
const mood = computed(() => petting.value && ['idle', 'guide', 'success', 'sleep'].includes(props.mood) ? 'celebrate' : sleeping.value && props.mood === 'idle' ? 'sleep' : props.mood);
const index = computed(() => Math.max(0, poses.indexOf(mood.value)));
// Generated atlas has irregular pose widths; explicit viewports avoid neighbour bleed.
const bounds = ['35 48 420 414','515 45 365 418','915 65 422 403','1370 60 386 407','15 496 485 370','535 510 330 354','935 485 374 385','1315 500 440 369'];
const frame = computed(() => {const [, , w, h] = bounds[index.value].split(' ').map(Number);const scale=460/Math.max(w,h);return {x:(480-w*scale)/2,y:(480-h*scale)/2,width:w*scale,height:h*scale};});
const atlas = `${import.meta.env.BASE_URL}art/xiaohu-watercolor-atlas-v4.png`;
let petTimer, sleepTimer;
function pet() { sleeping.value = false; petting.value = true; emit('pet'); clearTimeout(petTimer); petTimer = setTimeout(() => petting.value = false, 1500); }
onMounted(() => { sleepTimer = setTimeout(() => sleeping.value = true, 45000); });
onBeforeUnmount(() => { clearTimeout(petTimer); clearTimeout(sleepTimer); });
</script>
<template>
  <button type="button" class="crystal-cat watercolor-cat" :class="[{small}, `cat-${mood}`]" :aria-label="`小护：${labels[index]}，点击摸摸它`" :data-mood="mood" @click="pet">
    <svg class="cat-sprite" viewBox="0 0 480 480" role="img" :aria-label="labels[index]"><svg :viewBox="bounds[index]" v-bind="frame" overflow="hidden"><image :href="atlas" width="1774" height="887" /></svg></svg>
  </button>
</template>
<style scoped>
.crystal-cat{display:block;width:240px;max-width:100%;padding:0;border:0;background:none;cursor:pointer;aspect-ratio:1}
.crystal-cat.small{width:120px;margin:auto}
.cat-sprite{display:block;width:100%;height:100%;overflow:hidden}
.cat-celebrate .cat-sprite{animation:happy-hop .55s ease-in-out 2}
.cat-thinking .cat-sprite{animation:ponder 4s ease-in-out infinite}
.cat-analyzing .cat-sprite{animation:ponder 2.5s ease-in-out infinite}
@keyframes happy-hop{50%{transform:translateY(-9px) rotate(-3deg)}}
@keyframes ponder{50%{transform:translateY(-3px)}}
@media(prefers-reduced-motion:reduce){.cat-sprite{animation:none!important}}
</style>
