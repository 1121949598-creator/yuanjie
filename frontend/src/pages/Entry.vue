<script setup>
import { ref } from 'vue';
import { journeys } from '../journeys';
import RiverArt from '../components/RiverArt.vue';
import RiverBoat from '../components/RiverBoat.vue';
import Brand from '../components/Brand.vue';
const mode = ref('download');
</script>
<template>
  <div class="entry-page">
    <div class="entry-river"><RiverArt /><RiverBoat /></div>
    <header><Brand /><RouterLink to="/">回到首页</RouterLink></header>
    <main class="entry-layout">
      <section class="entry-card"><h2>欢迎来到 源界</h2><p>选择你这次要检查的内容。</p><fieldset><legend>使用场景</legend><label v-for="(item,key) in journeys" :key="key" :class="{selected:mode===key}"><input type="radio" name="journey" :value="key" v-model="mode"><span><b>{{ item.title }}</b><small>{{ item.audience }}</small></span></label></fieldset><RouterLink class="button primary" :to="`/new?mode=${mode}`">进入检查工作台</RouterLink><div class="entry-local"><b>本地版</b></div></section>
      <section class="entry-story"><h1>从源码出发，<br>看清风险。</h1><p>核对声明、能力与证据，<br>再决定安装或发布。</p></section>
    </main>
  </div>
</template>
<style scoped>
.entry-layout { grid-template-columns: minmax(0, 430px) minmax(0, 1fr); gap: 6vw; margin: 24px auto 80px; align-items: start; }
.entry-story { padding: 12px 0 0 12px; }
.entry-story h1 { font-size: clamp(32px, 3.8vw, 52px); }
.entry-card { min-width: 0; }
@media (max-width: 760px) {
  .entry-layout { grid-template-columns: minmax(0, 1fr); gap: 16px; padding: 0 22px; margin: 16px auto 100px; }
  .entry-story { padding: 0; }
  .entry-story h1 { font-size: 30px; margin: 12px 0; }
}
</style>
