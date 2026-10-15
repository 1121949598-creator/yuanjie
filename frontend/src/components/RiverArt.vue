<script setup>
import { computed } from "vue";
import RiverFlow from './RiverFlow.vue';
const props = defineProps({ variant: { type: String, default: "home" } });
const artwork = computed(
  () => `${import.meta.env.BASE_URL}art/${({home:'page-home-water-v4.png', upload:'page-upload-v3.png',download:'reference-current-3.jpg',agent:'reference-current-4.jpg',history:'reference-current-3.jpg',scan:'reference-current-4.jpg',report:'reference-current-5.jpg'})[props.variant] || 'page-upload-v3.png'}`,
);
</script>
<template>
  <div class="page-art" :data-art="variant" aria-hidden="true">
    <img :src="artwork" alt="" decoding="async" draggable="false" />
    <RiverFlow v-if="variant === 'home'" />
  </div>
</template>
<style scoped>
.page-art {
  position: relative;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.page-art img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: fill;
}
.page-art:not([data-art="home"]):not([data-art="upload"]) img {object-fit:cover;object-position:right center;opacity:.38}
</style>
