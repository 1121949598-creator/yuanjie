<script setup>
import CrystalCat from '../components/WatercolorCat.vue';
const moods = [['idle','默认站立'],['thinking','思考中'],['analyzing','正在分析'],['success','成功完成'],['guide','引导提示'],['warning','警告提醒'],['celebrate','庆祝鼓励'],['sleep','躺平休息']];
</script>
<template><section class="mascot-gallery"><div class="page-heading"><div><h1>小护的八种心情</h1><p>把清流的颜色，带到每一次检查里。点击小护，可以和它打个招呼。</p></div></div><div class="mascot-poses"><figure v-for="[mood,label] in moods" :key="mood"><CrystalCat :mood="mood"/><figcaption>{{ label }}</figcaption></figure></div><RouterLink to="/">回到首页</RouterLink></section></template>
