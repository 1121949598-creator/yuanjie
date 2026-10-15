<script setup>
import {computed, inject, onBeforeUnmount, onMounted, ref, watch} from 'vue';
import {useRouter} from 'vue-router';
import Icon from '../components/Icon.vue';
import ScanProgress from '../components/ScanProgress.vue';
import {api, encode, uploadScan} from '../api';
import {journeys, rememberJourney} from '../journeys';
import {exampleFlow} from '../example-flow';
import {assistant, resetAssistant} from '../assistant';

const router=useRouter(), mode=ref('project');
const search=ref(''), examples=ref([]), loading=ref(true), error=ref('');
const busy=ref(false), phase=ref(''), progress=ref(0), seconds=ref(0), selectedName=ref('');
const filtered=computed(()=>examples.value.filter(item=>(item.title+item.description).toLowerCase().includes(search.value.trim().toLowerCase())));
const setArtwork=inject('page-artwork',()=>{});
let clock, mounted=true;
watch([busy,phase,error],()=>{Object.assign(assistant,{phase:busy.value?phase.value:'',fileReady:false,error:error.value});setArtwork(busy.value?'scan':null);},{immediate:true});
async function loadExamples(){
  loading.value=true;error.value='';
  try{examples.value=(await api('/examples')).items;}catch(e){error.value=e.message;}finally{loading.value=false;}
}
onMounted(loadExamples);
onBeforeUnmount(()=>{mounted=false;clearInterval(clock);resetAssistant();setArtwork(null);});
async function start(item){
  if(busy.value)return;
  const flow=exampleFlow(item.id), selectedMode=flow.mode, selectedJourney=journeys[selectedMode];
  mode.value=selectedMode;
  busy.value=true;error.value='';phase.value='analyzing';progress.value=0;seconds.value=0;selectedName.value=item.title;
  clock=setInterval(()=>seconds.value++,1000);
  try{
    const response=await fetch(`/api/examples/${encode(item.id)}/archive`);
    if(!response.ok)throw new Error('示例文件暂时无法读取，请重试。');
    const source=new File([await response.blob()],`synthetic-${item.id}.zip`,{type:'application/zip'});
    phase.value='uploading';
    const result=await uploadScan(source,p=>progress.value=p,()=>phase.value='analyzing',selectedJourney.scene,selectedMode);
    rememberJourney(result.scan_id,selectedMode,flow.section);
    if(mounted)await router.push(`/scan/${result.scan_id}/${flow.section}?mode=${selectedMode}`);
  }catch(e){error.value=e.message;busy.value=false;}finally{clearInterval(clock);}
}
</script>
<template>
  <ScanProgress v-if="busy" :phase="phase" :selected-name="selectedName" :progress="progress" :seconds="seconds" :mode="mode" />
  <div v-else class="examples-page">
    <div class="page-heading">
      <div><h1>已有示例</h1><p>还没准备好源码？先用一个合成例子体验检查流程。点击运行会实际扫描，也可以下载 ZIP 查看代码。</p></div>
    </div>
    <div class="examples-controls">
      <label class="example-search"><Icon name="Search" :size="16" /><input v-model="search" placeholder="找个示例…" aria-label="搜索合成示例" /></label>
    </div>
    <p class="examples-context">按想体验的功能选择示例，扫描后自动打开对应结果页。合成示例不是真实病毒，不验证外部凭据，也不执行目标代码。</p>
    <div v-if="error" class="alert error" role="alert"><span>{{ error }}</span><button class="text-button" @click="loadExamples">重新读取示例</button></div>
    <p v-if="loading" class="muted" role="status">正在读取示例…</p>
    <section v-else class="examples-section" aria-label="合成示例列表">
      <div class="example-grid">
        <article v-for="(item,index) in filtered" :key="item.id" class="example-card">
          <span class="example-number">0{{ index+1 }}</span><span class="example-icon"><Icon :name="exampleFlow(item.id).icon" :size="25" /></span>
          <h3>{{ item.title }}</h3><p>{{ exampleFlow(item.id).label }}：{{ item.description }}</p>
          <div><button class="text-button" @click="start(item)">运行示例 <Icon name="ArrowUpRight" :size="16" /></button><a :href="`/api/examples/${encode(item.id)}/archive`" class="icon-button" :aria-label="`下载${item.title}样例 ZIP`"><Icon name="Download" :size="16" /></a></div>
        </article>
      </div>
      <p v-if="!error && !filtered.length" class="examples-empty">{{ search ? '没找到这个例子。试试“凭据”“研究”或“MCP”。' : '当前没有可用示例，请稍后重新读取。' }}</p>
    </section>
  </div>
</template>
<style scoped>
.examples-controls {display:flex;justify-content:flex-end;}
.examples-context {margin:16px 0 0;font-size:13px;line-height:1.8;color:#4d6978;}
.examples-section {margin-top:24px;}
@media(max-width:760px){.example-search{width:100%;}}
</style>
