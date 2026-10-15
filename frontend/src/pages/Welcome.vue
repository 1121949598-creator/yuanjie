<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import Brand from "../components/Brand.vue";
import Icon from "../components/Icon.vue";
import CrystalCat from "../components/WatercolorCat.vue";
import RiverArt from "../components/RiverArt.vue";
import RiverBoat from "../components/RiverBoat.vue";
import { state, loadSystem } from "../state";
const index = ref(0),
  visible = ref(true);
const steps = [
  {
    title: "你好，我是小护。",
    text: "下载的工具、自己的项目，或专业 Agent？选一条适合你的路线，我陪你看清风险。",
    mood: "guide",
  },
  {
    title: "从一个 ZIP 开始。",
    text: "选择安装前或发布前检查，再上传源码 ZIP。我们静态读取文件，不安装依赖，也不运行你的代码。",
    mood: "thinking",
  },
  {
    title: "它说的，和它能做的一样吗？",
    text: "除了凭据、许可证和 Agent 风险，我们还会对照组件声明与 Shell、文件、网络等能力，保留源码证据。",
    mood: "analyzing",
  },
  {
    title: "一起看懂结果。",
    text: "关系分为关联合理、待复核、不一致和证据不足。模型有没有参与、还有哪些检查缺口，报告都会告诉你。",
    mood: "success",
  },
];
const step = computed(() => steps[index.value]);
let timer;
function next() {
  index.value = (index.value + 1) % steps.length;
}
onMounted(() => {
  loadSystem();
  timer = setInterval(() => {
    if (visible.value && index.value < 3) index.value++;
  }, 16000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <div class="river-welcome">
    <div class="welcome-current"><RiverArt /><RiverBoat /></div>
    <header class="river-header">
      <Brand />
    </header>
    <main>
      <section class="river-hero">
        <div class="river-copy">
          <p class="river-kicker">安装前看得懂，发布前查得清</p>
          <h1>让安全，<br />像一股清流。</h1>
          <p class="river-lead">
            用别人分享的工具，也分享自己的想法。<br />从引入到发布，每一次出发，都先看清风险。
          </p>
          <div class="hero-actions">
            <RouterLink to="/entry" class="button primary">开始使用 <Icon name="ArrowRight" :size="19" /></RouterLink>
          </div>
          <div class="welcome-service">
            <span class="status-dot" :class="{ offline: !state.system }"></span
            >{{
              state.system ? "本地服务已连接，随时可以开始" : "本地服务未连接"
            }}<button
              v-if="!state.system"
              class="text-button"
              @click="loadSystem"
            >
              重试
            </button>
          </div>
          <p class="hero-footnote">
            不执行目标代码 · 凭据脱敏展示 · 每个判断都有迹可循
          </p>
        </div>
        <div class="river-companion">
          <p class="river-handwriting">更安全的旅程，从这里开始。</p>
          <div class="cat-halo"></div>
          <CrystalCat
            :mood="visible ? step.mood : 'idle'"
            @pet="visible = true"
          /><RouterLink to="/mascot" class="cat-caption">小护的八种心情 · 看看我</RouterLink>
          <div v-if="visible" class="cat-intro">
            <button
              class="icon-button intro-close"
              aria-label="收起介绍"
              @click="visible = false"
            >
              <Icon name="X" :size="16" />
            </button>
            <div aria-live="polite">
              <h3>{{ step.title }}</h3>
              <p>{{ step.text }}</p>
            </div>
            <div class="intro-bottom">
              <div class="intro-dots">
                <button
                  v-for="(item, i) in steps"
                  :key="i"
                  :class="{ active: i === index }"
                  :aria-label="`第 ${i + 1} 段介绍`"
                  :aria-pressed="i === index"
                  @click="index = i"
                ></button>
              </div>
              <button class="text-button" @click="next">
                {{ index === 3 ? "再听一遍" : "接着说" }}
                <Icon name="ArrowRight" :size="15" />
              </button>
            </div>
          </div>
          <button v-else class="button secondary" @click="visible = true">
            让小护介绍一下
          </button>
        </div>
      </section>
      <section id="what-we-check" class="river-features">
        <div>
          <span>01 / SECRET</span><Icon name="KeyRound" />
          <h3>守住你的凭据</h3>
          <p>定位源码与配置中的疑似密钥，<br />只展示脱敏后的证据。</p>
        </div>
        <div>
          <span>02 / LICENSE</span><Icon name="FileCheck2" />
          <h3>理清开源来源</h3>
          <p>查看许可证、依赖与覆盖情况，<br />区分检查结果和检查缺口。</p>
        </div>
        <div>
          <span>03 / AGENT</span><Icon name="Bot" />
          <h3>看清工具权限</h3>
          <p>梳理任务、工具和绑定关系，<br />追溯敏感能力的来源。</p>
        </div>
        <div>
          <span>04 / ALIGNMENT</span><Icon name="GitCompareArrows" />
          <h3>核对所言与所行</h3>
          <p>对照组件声明和真实静态能力，<br />让不一致与不确定都被看见。</p>
        </div>
      </section>
    </main>
    <footer class="river-footer">
      <b>源界</b><span>FOR A SAFER, BRIGHTER, OPEN WORLD.</span
      ><span>开源的力量，守护每一次出发。</span>
    </footer>
  </div>
</template>
