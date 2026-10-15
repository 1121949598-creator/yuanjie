<script setup>
import { computed, onMounted, onBeforeUnmount, ref, useId } from "vue";
const props = defineProps({
  mood: { type: String, default: "idle" },
  small: Boolean,
});
const emit = defineEmits(["pet"]);
const id = useId().replaceAll(":", "");
const el = ref(null),
  eyeX = ref(0),
  eyeY = ref(0),
  blink = ref(false),
  petting = ref(false),
  sleeping = ref(false);
let blinkTimer, closeTimer, petTimer, restTimer;
const mood = computed(() =>
  petting.value
    ? "celebrate"
    : sleeping.value && props.mood === "idle"
      ? "sleep"
      : props.mood,
);
const paint = (name) => `url(#${id}-${name})`;
function look(e) {
  if (!el.value) return;
  const b = el.value.getBoundingClientRect();
  eyeX.value = Math.max(
    -5,
    Math.min(5, (e.clientX - b.left - b.width / 2) / 35),
  );
  eyeY.value = Math.max(
    -3,
    Math.min(4, (e.clientY - b.top - b.height * 0.42) / 50),
  );
  sleeping.value = false;
  clearTimeout(restTimer);
  restTimer = setTimeout(() => (sleeping.value = true), 45000);
}
function pet() {
  petting.value = true;
  emit("pet");
  clearTimeout(petTimer);
  petTimer = setTimeout(() => (petting.value = false), 1800);
}
function scheduleBlink() {
  blinkTimer = setTimeout(
    () => {
      blink.value = true;
      closeTimer = setTimeout(() => {
        blink.value = false;
        scheduleBlink();
      }, 170);
    },
    3100 + Math.random() * 2200,
  );
}
onMounted(() => {
  window.addEventListener("pointermove", look, { passive: true });
  scheduleBlink();
  restTimer = setTimeout(() => (sleeping.value = true), 45000);
});
onBeforeUnmount(() => {
  window.removeEventListener("pointermove", look);
  [blinkTimer, closeTimer, petTimer, restTimer].forEach(clearTimeout);
});
</script>
<template>
  <button
    ref="el"
    type="button"
    class="crystal-cat"
    :class="[{ small }, `cat-${mood}`, { 'cat-blink': blink }]"
    aria-label="摸摸小护猫猫"
    @click="pet"
  >
    <svg viewBox="0 0 360 380" role="img" aria-label="晶莹的胖胖猫猫小护">
      <defs>
        <linearGradient :id="`${id}-glass`" x1=".05" y1="0" x2=".8" y2="1">
          <stop stop-color="#ffffff" />
          <stop offset=".2" stop-color="#e8e6ff" />
          <stop offset=".5" stop-color="#bebafa" />
          <stop offset=".78" stop-color="#e6dafa" />
          <stop offset="1" stop-color="#f2ffff" />
        </linearGradient>
        <radialGradient :id="`${id}-pearl`" cx=".27" cy=".67" r=".72">
          <stop stop-color="#fffacb" />
          <stop offset=".26" stop-color="#ffe8f4" />
          <stop offset=".55" stop-color="#d8c4ff" stop-opacity=".8" />
          <stop offset="1" stop-color="#737eda" stop-opacity="0" />
        </radialGradient>
        <radialGradient :id="`${id}-blue`" cx=".7" cy=".7">
          <stop stop-color="#c9f9ff" stop-opacity=".9" />
          <stop offset="1" stop-color="#beaffc" stop-opacity="0" />
        </radialGradient>
        <linearGradient :id="`${id}-shield`" x1="0" y1="0" x2="1" y2="1">
          <stop stop-color="#a6e5ff" stop-opacity=".83" />
          <stop offset=".5" stop-color="#7d83ec" stop-opacity=".85" />
          <stop offset="1" stop-color="#c5a2ee" stop-opacity=".65" />
        </linearGradient>
        <filter :id="`${id}-glow`" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
        <filter :id="`${id}-soft`"><feGaussianBlur stdDeviation="2" /></filter>
      </defs>
      <ellipse
        cx="180"
        cy="349"
        rx="100"
        ry="15"
        fill="#839bd8"
        opacity=".14"
        :filter="paint('glow')"
      />
      <ellipse
        cx="180"
        cy="348"
        rx="105"
        ry="10"
        fill="none"
        stroke="#8eabe7"
        stroke-width="1"
        opacity=".3"
      />
      <g class="cat-body">
        <path
          class="cat-tail"
          d="M247 309 C317 312 299 232 276 250 C258 264 315 283 265 294"
          :stroke="paint('glass')"
          stroke-width="24"
          stroke-linecap="round"
          fill="none"
        />
        <path
          d="M123 218 Q100 264 115 327 Q133 346 181 332 Q229 348 252 327 Q262 265 232 219Z"
          :fill="paint('glass')"
          stroke="#f6faff"
          stroke-width="2"
        />
        <ellipse cx="181" cy="276" rx="59" ry="59" :fill="paint('pearl')" />
        <ellipse cx="205" cy="286" rx="43" ry="51" :fill="paint('blue')" />
        <path
          d="M130 292Q116 311 126 330Q143 342 157 330L158 310 M214 291Q208 319 215 332Q234 341 246 327L244 307"
          :fill="paint('glass')"
          stroke="#f5f7ff"
          stroke-width="1.8"
        />
        <g class="cat-head">
          <path
            d="M76 124 L84 47 Q86 30 99 43 L144 93 Q178 83 213 92 L261 48 Q275 35 278 55 L283 138 Q306 200 270 229 Q235 253 182 251 Q126 253 93 229 Q56 204 76 124Z"
            :fill="paint('glass')"
            stroke="#fbffff"
            stroke-width="2.6"
          />
          <path
            class="cat-ear left"
            d="M90 103 L94 57 L128 100Z"
            fill="#e0cdfa"
            opacity=".8"
          />
          <path
            class="cat-ear right"
            d="M232 101 L267 60 L268 120Z"
            fill="#e0cdfa"
            opacity=".8"
          />
          <ellipse cx="180" cy="173" rx="101" ry="76" :fill="paint('pearl')" />
          <ellipse cx="218" cy="188" rx="61" ry="60" :fill="paint('blue')" />
          <path
            d="M85 119Q82 166 88 182 M102 45L137 94 M269 62L270 102"
            fill="none"
            stroke="white"
            stroke-width="4"
            stroke-linecap="round"
            opacity=".73"
            :filter="paint('soft')"
          />
          <g
            class="cat-eyes-open"
            :style="{ transform: `translate(${eyeX}px,${eyeY}px)` }"
          >
            <ellipse
              cx="137"
              cy="168"
              rx="9"
              ry="16"
              fill="#33304e"
              transform="rotate(5 137 168)"
            />
            <ellipse
              cx="222"
              cy="168"
              rx="9"
              ry="16"
              fill="#33304e"
              transform="rotate(-5 222 168)"
            />
            <ellipse
              cx="135"
              cy="161"
              rx="2"
              ry="3"
              fill="#fff"
              opacity=".45"
            />
            <ellipse
              cx="220"
              cy="161"
              rx="2"
              ry="3"
              fill="#fff"
              opacity=".45"
            />
          </g>
          <g
            class="cat-eyes-closed"
            stroke="#4b3d66"
            stroke-width="4.5"
            stroke-linecap="round"
            fill="none"
          >
            <path d="M128 168Q137 158 146 168 M213 168Q222 158 231 168" />
          </g>
          <ellipse
            cx="114"
            cy="193"
            rx="16"
            ry="7"
            fill="#f1adc9"
            opacity=".3"
          />
          <ellipse
            cx="244"
            cy="193"
            rx="16"
            ry="7"
            fill="#f1adc9"
            opacity=".3"
          />
          <path
            d="M173 201Q181 209 189 201"
            fill="none"
            stroke="#9c759e"
            stroke-width="2.6"
            stroke-linecap="round"
          />
        </g>
        <g class="cat-shield">
          <path
            d="M168 230L210 247L207 288Q198 310 169 327Q140 312 129 289L126 248Z"
            :fill="paint('shield')"
            stroke="#e3f7ff"
            stroke-width="3"
          />
          <path
            d="M168 241L199 254L197 285Q188 305 169 315Q150 303 141 284L137 256Z"
            fill="none"
            stroke="#ddf4ff"
            stroke-width="1"
            opacity=".8"
          />
          <path
            d="M156 274V264a13 13 0 0126 0V274"
            fill="none"
            stroke="#e8faff"
            stroke-width="6"
          />
          <rect x="148" y="272" width="43" height="33" rx="8" fill="#d1e6ff" />
          <path
            d="M169 283V294"
            stroke="#7474c4"
            stroke-width="5"
            stroke-linecap="round"
          />
        </g>
        <path
          class="cat-paw"
          d="M117 250Q97 260 111 280Q124 288 136 270"
          :fill="paint('glass')"
          stroke="#f2f2ff"
          stroke-width="2"
        />
      </g>
      <g v-if="mood === 'analyzing'" class="cat-panel">
        <rect
          x="91"
          y="253"
          width="178"
          height="70"
          rx="12"
          fill="#607fca"
          fill-opacity=".87"
          stroke="#b9e7fa"
          stroke-width="2"
        />
        <g stroke="#c7edff" stroke-width="4" stroke-linecap="round">
          <path d="M107 270h10m10 0h76M107 285h10m10 0h55M107 300h10m10 0h87" />
        </g>
        <circle
          class="cat-scan-ring"
          cx="244"
          cy="289"
          r="14"
          fill="none"
          stroke="#c3f3ff"
          stroke-dasharray="18 8"
          stroke-width="3"
        />
      </g>
      <text
        v-if="mood === 'thinking'"
        x="283"
        y="107"
        fill="#8473c9"
        font-size="44"
        font-weight="700"
      >
        ?
      </text>
      <g v-if="mood === 'warning'" transform="translate(260 243)">
        <path
          d="M0 0L33 58H-33Z"
          fill="#fff3d6"
          stroke="#d99442"
          stroke-width="3"
          stroke-linejoin="round"
        />
        <text
          text-anchor="middle"
          y="45"
          fill="#ac6b27"
          font-size="33"
          font-weight="800"
        >
          !
        </text>
      </g>
      <g v-if="mood === 'celebrate' || mood === 'success'" class="cat-love">
        <path
          d="M182 55C152 23 174 7 185 28C202 7 222 25 182 55Z"
          fill="#e7a1c3"
        />
        <path
          d="M64 211l4-11 4 11 11 4-11 4-4 11-4-11-11-4Z M290 177l4-10 4 10 10 4-10 4-4 10-4-10-10-4Z"
          fill="#e6bc61"
        />
      </g>
      <text
        v-if="mood === 'sleep'"
        x="260"
        y="127"
        fill="#8e85bd"
        font-size="27"
      >
        z Z
      </text>
    </svg>
  </button>
</template>
<style scoped>
.crystal-cat {
  display: block;
  position: relative;
  width: 360px;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.crystal-cat svg {
  width: 100%;
  height: auto;
  overflow: visible;
}
.crystal-cat.small {
  width: 170px;
  margin: auto;
}
.cat-body {
  transform-origin: 180px 327px;
  animation: cat-breathe 4.5s ease-in-out infinite;
}
.cat-head {
  transform-origin: 180px 220px;
  transition: transform 0.6s;
}
.cat-eyes-open {
  transition: transform 0.22s ease-out;
}
.cat-eyes-closed {
  display: none;
}
.cat-blink .cat-eyes-open,
.cat-success .cat-eyes-open,
.cat-celebrate .cat-eyes-open,
.cat-sleep .cat-eyes-open {
  display: none;
}
.cat-blink .cat-eyes-closed,
.cat-success .cat-eyes-closed,
.cat-celebrate .cat-eyes-closed,
.cat-sleep .cat-eyes-closed {
  display: block;
}
.cat-ear {
  transform-box: fill-box;
  transform-origin: center bottom;
  animation: ear-twitch 8s ease-in-out infinite;
}
.cat-ear.right {
  animation-delay: 0.3s;
}
.cat-tail {
  transform-origin: 250px 311px;
  animation: tail-wave 5s ease-in-out infinite;
}
.cat-thinking .cat-head,
.cat-warning .cat-head {
  transform: rotate(9deg);
}
.cat-celebrate .cat-body {
  animation: cat-hop 0.65s ease-in-out 2;
}
.cat-guide .cat-paw {
  transform-origin: 115px 250px;
  animation: paw-wave 1s ease-in-out 3;
}
.cat-analyzing .cat-shield {
  opacity: 0;
}
.cat-love {
  animation: love-rise 1.8s ease-out both;
  transform-origin: center;
}
.cat-scan-ring {
  transform-origin: 244px 289px;
  animation: rotate-ring 3s linear infinite;
}
.cat-sleep .cat-body {
  transform: translateY(25px) rotate(-12deg) scaleY(0.87);
  animation: none;
}
@keyframes cat-breathe {
  50% {
    transform: translateY(-5px) scaleY(1.012);
  }
}
@keyframes ear-twitch {
  0%,
  87%,
  100% {
    transform: rotate(0);
  }
  90%,
  96% {
    transform: rotate(9deg);
  }
  93% {
    transform: rotate(-6deg);
  }
}
@keyframes tail-wave {
  50% {
    transform: rotate(-9deg);
  }
}
@keyframes paw-wave {
  50% {
    transform: rotate(-24deg);
  }
}
@keyframes cat-hop {
  50% {
    transform: translateY(-17px) rotate(-3deg);
  }
}
@keyframes love-rise {
  0% {
    opacity: 0;
    transform: translateY(25px) scale(0.65);
  }
  30% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translateY(-18px) scale(1.1);
  }
}
@keyframes rotate-ring {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .crystal-cat * {
    animation: none !important;
    transition: none !important;
  }
}
</style>
