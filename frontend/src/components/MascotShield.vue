<!-- Archived interactive shield mascot retained as a reusable visual direction. -->
<script setup>
import { ref, onMounted, onBeforeUnmount, useId } from "vue";
defineProps({ small: Boolean, mood: { default: "happy" } });
const uid = useId();
const paint = (name) => `url(#${uid}-${name})`;
const mascot = ref(null),
  x = ref(0),
  y = ref(0),
  blink = ref(false),
  greet = ref(false),
  hovered = ref(false),
  protecting = ref(false),
  reduced = ref(false);
let timer,
  blinkTimer,
  helloTimer,
  preference,
  greetings = 0;
function move(event) {
  if (reduced.value || !mascot.value) return;
  const b = mascot.value.getBoundingClientRect();
  const dx = event.clientX - b.left - b.width / 2;
  const dy = event.clientY - b.top - b.height * 0.47;
  const distance = Math.hypot(dx, dy) || 1;
  const amount = Math.min(6, distance / 32);
  x.value = (dx / distance) * amount;
  y.value = (dy / distance) * amount;
}
function wave() {
  greetings += 1;
  greet.value = true;
  protecting.value = greetings % 2 === 0;
  clearTimeout(helloTimer);
  helloTimer = setTimeout(() => {
    greet.value = false;
    protecting.value = false;
  }, 1400);
}
function motionPreference() {
  reduced.value = preference.matches;
  if (reduced.value) {
    x.value = 0;
    y.value = 0;
    blink.value = false;
  }
}
onMounted(() => {
  preference = matchMedia("(prefers-reduced-motion: reduce)");
  motionPreference();
  preference.addEventListener("change", motionPreference);
  window.addEventListener("pointermove", move, { passive: true });
  timer = setInterval(() => {
    if (reduced.value) return;
    blink.value = true;
    blinkTimer = setTimeout(() => (blink.value = false), 160);
  }, 4300);
});
onBeforeUnmount(() => {
  window.removeEventListener("pointermove", move);
  preference?.removeEventListener("change", motionPreference);
  clearInterval(timer);
  clearTimeout(blinkTimer);
  clearTimeout(helloTimer);
});
</script>

<template>
  <button
    ref="mascot"
    class="mascot shield-mascot"
    :class="{ small, greet, protecting, hovered }"
    @click="wave"
    @pointerenter="hovered = true"
    @pointerleave="hovered = false"
    @focus="hovered = true"
    @blur="hovered = false"
    aria-label="和小护打个招呼"
    title="点一下挥手，再点一下开启守护光环"
  >
    <svg
      viewBox="0 0 360 310"
      role="img"
      aria-label="蓝色盾牌小护，眼睛会跟随鼠标，点击挥手或亮起守护光环"
    >
      <defs>
        <linearGradient :id="`${uid}-rim`" x1="0" y1="0" x2=".8" y2="1">
          <stop stop-color="#b1f2ff" />
          <stop offset=".3" stop-color="#629dff" />
          <stop offset="1" stop-color="#3b51c9" />
        </linearGradient>
        <linearGradient :id="`${uid}-blue`" x1="0" y1="0" x2=".8" y2="1">
          <stop stop-color="#62bdff" />
          <stop offset=".48" stop-color="#3d82ed" />
          <stop offset="1" stop-color="#5363db" />
        </linearGradient>
        <linearGradient :id="`${uid}-face`" x1="0" y1="0" x2=".5" y2="1">
          <stop stop-color="#fff" />
          <stop offset="1" stop-color="#dceeff" />
        </linearGradient>
        <linearGradient :id="`${uid}-glove`" x1="0" y1="0" x2=".6" y2="1">
          <stop stop-color="#fff" />
          <stop offset="1" stop-color="#b6d9ff" />
        </linearGradient>
        <linearGradient :id="`${uid}-eye`" x1="0" y1="0" x2="0" y2="1">
          <stop stop-color="#172b55" />
          <stop offset="1" stop-color="#366eb2" />
        </linearGradient>
        <filter
          :id="`${uid}-soft`"
          x="-30%"
          y="-100%"
          width="160%"
          height="300%"
        >
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      <ellipse
        cx="180"
        cy="282"
        rx="79"
        ry="10"
        fill="#6689d1"
        opacity=".2"
        :filter="paint('soft')"
      />
      <g class="guard-ring" fill="none" stroke="#66beff" stroke-width="2">
        <ellipse cx="180" cy="177" rx="144" ry="117" />
        <ellipse
          cx="180"
          cy="177"
          rx="153"
          ry="125"
          stroke-dasharray="3 13"
          opacity=".5"
        />
      </g>
      <g class="mascot-body">
        <g class="shield-tilt" :style="{ transform: `rotate(${x * 0.48}deg)` }">
          <!-- Short boots sit behind the tapered shield, preserving its silhouette. -->
          <path
            d="M141 241L135 266M219 241L225 266"
            stroke="#476bd5"
            stroke-width="14"
            stroke-linecap="round"
          />
          <path
            d="M135 258C122 256 111 263 111 273Q112 280 126 280H151Q161 278 157 270L151 260Z"
            :fill="paint('blue')"
          />
          <path
            d="M225 258C238 256 249 263 249 273Q248 280 234 280H209Q199 278 203 270L209 260Z"
            :fill="paint('blue')"
          />
          <path
            d="M116 276H152M208 276H244"
            stroke="#c5eaff"
            stroke-width="3"
            stroke-linecap="round"
          />
          <g class="left-hand">
            <path
              d="M83 166Q64 167 56 184"
              fill="none"
              stroke="#578ae6"
              stroke-width="13"
              stroke-linecap="round"
            />
            <path
              d="M58 173C50 167 41 173 39 183C35 181 31 184 33 190C36 203 47 208 57 201Q69 192 64 182Z"
              :fill="paint('glove')"
              stroke="#83b5ec"
              stroke-width="2"
            />
          </g>
          <g class="right-hand">
            <path
              d="M277 168Q294 165 301 145"
              fill="none"
              stroke="#578ae6"
              stroke-width="13"
              stroke-linecap="round"
            />
            <path
              d="M296 150C286 145 288 137 294 138L298 140L295 126Q294 119 299 119Q303 119 305 131L306 119Q307 113 312 116L314 132Q320 119 324 124L321 142Q330 136 332 142C334 153 320 166 309 162Z"
              :fill="paint('glove')"
              stroke="#83b5ec"
              stroke-width="2"
              stroke-linejoin="round"
            />
            <path
              d="M300 149Q307 145 313 149"
              fill="none"
              stroke="#a3c9ee"
              stroke-width="2"
              stroke-linecap="round"
            />
          </g>
          <!-- Raised crest, broad shoulders and a rounded point read as a shield at every size. -->
          <path
            d="M180 32C203 45 233 54 268 59Q283 61 282 78L278 153C274 207 239 243 190 266Q180 271 170 266C121 243 86 207 82 153L78 78Q77 61 92 59C127 54 157 45 180 32Z"
            fill="#3e59bd"
            transform="translate(0 5)"
          />
          <path
            class="shield-outline"
            d="M180 27C203 40 233 49 268 54Q283 56 282 73L278 148C274 202 239 238 190 261Q180 266 170 261C121 238 86 202 82 148L78 73Q77 56 92 54C127 49 157 40 180 27Z"
            :fill="paint('rim')"
            stroke="#c7ebff"
            stroke-width="2"
          />
          <path
            d="M180 42C207 56 237 63 262 67Q270 68 269 78L265 147C261 194 232 225 185 249Q180 252 175 249C128 225 99 194 95 147L91 78Q90 68 98 67C123 63 153 56 180 42Z"
            :fill="paint('blue')"
            stroke="#3772d5"
            stroke-width="2"
          />
          <path
            d="M105 77Q145 70 177 55"
            fill="none"
            stroke="#e1faff"
            stroke-width="5"
            stroke-linecap="round"
            opacity=".8"
          />
          <path
            d="M98 96L100 123"
            fill="none"
            stroke="#c4efff"
            stroke-width="4"
            stroke-linecap="round"
            opacity=".5"
          />
          <path
            d="M180 53Q216 72 254 77L251 146Q246 208 184 240"
            fill="none"
            stroke="#92c7ff"
            stroke-width="2"
            opacity=".45"
          />
          <!-- A soft face inset leaves the shield silhouette clear. -->
          <path
            d="M116 111Q180 91 244 111Q253 114 252 127L249 160Q245 190 225 202Q180 225 135 202Q115 190 111 160L108 127Q107 114 116 111Z"
            :fill="paint('face')"
            stroke="#b3dfff"
            stroke-width="2"
          />
          <path
            d="M133 123Q142 118 151 122M210 122Q219 118 228 123"
            stroke="#5c85b7"
            stroke-width="3"
            fill="none"
            stroke-linecap="round"
          />
          <ellipse
            cx="128"
            cy="177"
            rx="12"
            ry="7"
            fill="#f0a6bf"
            opacity=".65"
          />
          <ellipse
            cx="232"
            cy="177"
            rx="12"
            ry="7"
            fill="#f0a6bf"
            opacity=".65"
          />
          <g v-if="!blink && mood !== 'sleep'" class="eyes">
            <g :transform="`translate(${x} ${y})`">
              <ellipse cx="148" cy="151" rx="14" ry="19" :fill="paint('eye')" />
              <ellipse
                v-if="!greet || protecting"
                cx="212"
                cy="151"
                rx="14"
                ry="19"
                :fill="paint('eye')"
              />
              <path
                v-else
                d="M201 155Q212 144 223 155"
                fill="none"
                stroke="#234875"
                stroke-width="5"
                stroke-linecap="round"
              />
              <ellipse cx="144" cy="144" rx="4.7" ry="6" fill="white" />
              <circle cx="153" cy="158" r="2.6" fill="#a5e8ff" />
              <g v-if="!greet || protecting">
                <ellipse cx="208" cy="144" rx="4.7" ry="6" fill="white" />
                <circle cx="217" cy="158" r="2.6" fill="#a5e8ff" />
              </g>
            </g>
          </g>
          <g
            v-else
            class="closed-eyes"
            fill="none"
            stroke="#234875"
            stroke-width="4"
            stroke-linecap="round"
          >
            <path d="M136 154Q148 164 160 154M200 154Q212 164 224 154" />
          </g>
          <g v-if="greet || hovered">
            <path
              d="M168 179Q180 184 192 179Q191 196 180 196Q169 196 168 179Z"
              fill="#284775"
            />
            <path d="M173 191Q180 186 187 191Q180 198 173 191" fill="#f399b8" />
          </g>
          <path
            v-else
            d="M169 181Q180 192 191 181"
            fill="none"
            stroke="#284775"
            stroke-width="3.5"
            stroke-linecap="round"
          />
          <g class="shield-badge">
            <circle cx="180" cy="228" r="13" fill="#c2efff" opacity=".2" />
            <path
              d="M173 228L178 233L188 222"
              fill="none"
              stroke="#e0fcff"
              stroke-width="4"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </g>
          <g class="shield-sparkles" fill="#8ad8ff">
            <path d="M63 83L66 92L75 95L66 98L63 107L60 98L51 95L60 92Z" />
            <path
              d="M300 62L303 69L310 72L303 75L300 82L297 75L290 72L297 69Z"
            />
            <circle cx="290" cy="214" r="3" />
          </g>
        </g>
      </g>
    </svg>
  </button>
</template>

<style scoped>
.shield-tilt {
  transform-origin: 180px 165px;
  transition: transform 0.35s ease-out;
}
.shield-mascot .right-hand {
  transform-origin: 277px 168px;
}
.shield-mascot.greet .right-hand {
  animation: shield-wave 0.32s ease-in-out 4 alternate;
}
.shield-mascot .left-hand {
  transform-origin: 83px 166px;
  transition: transform 0.3s;
}
.shield-mascot.hovered .left-hand {
  transform: rotate(12deg);
}
.shield-mascot.protecting .left-hand {
  transform: rotate(30deg);
}
.shield-badge {
  transform-origin: 180px 228px;
}
.shield-mascot.protecting .shield-badge {
  animation: badge-glow 0.7s ease-in-out 2;
}
.guard-ring {
  opacity: 0;
  transform-origin: 180px 177px;
}
.protecting .guard-ring {
  animation: guard-bloom 1.4s ease-out;
}
.shield-sparkles {
  opacity: 0.6;
  transition: opacity 0.25s;
}
.hovered .shield-sparkles,
.greet .shield-sparkles {
  opacity: 1;
}
@keyframes shield-wave {
  to {
    transform: rotate(-24deg);
  }
}
@keyframes guard-bloom {
  0% {
    opacity: 0;
    transform: scale(0.75);
  }
  25% {
    opacity: 0.75;
  }
  100% {
    opacity: 0;
    transform: scale(1.08);
  }
}
@keyframes badge-glow {
  50% {
    transform: scale(1.18);
    filter: drop-shadow(0 0 5px #b8faff);
  }
}
@media (prefers-reduced-motion: reduce) {
  .shield-tilt,
  .shield-mascot .left-hand {
    transform: none !important;
  }
  .protecting .guard-ring {
    opacity: 0.4;
  }
}
</style>
