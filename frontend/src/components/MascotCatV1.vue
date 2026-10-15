<!-- Archived first iridescent cat direction retained as a reusable reference. -->
<script setup>
import { ref, onMounted, onBeforeUnmount, useId } from "vue";

defineProps({ small: Boolean, mood: { default: "happy" } });
const uid = useId();
const paint = (name) => `url(#${uid}-${name})`;
const mascot = ref(null);
const x = ref(0);
const y = ref(0);
const blink = ref(false);
const greet = ref(false);
const hovered = ref(false);
const reduced = ref(false);
const reaction = ref(0);
let blinkTimer;
let reopenTimer;
let reactionTimer;
let preference;

function move(event) {
  if (reduced.value || !mascot.value) return;
  const box = mascot.value.getBoundingClientRect();
  const dx = event.clientX - box.left - box.width / 2;
  const dy = event.clientY - box.top - box.height * 0.43;
  const distance = Math.hypot(dx, dy) || 1;
  const amount = Math.min(6, distance / 30);
  x.value = (dx / distance) * amount;
  y.value = (dy / distance) * amount;
}

function scheduleBlink(delay = 3200 + Math.random() * 2100) {
  clearTimeout(blinkTimer);
  if (reduced.value) return;
  blinkTimer = setTimeout(() => {
    blink.value = true;
    reopenTimer = setTimeout(() => {
      blink.value = false;
      scheduleBlink();
    }, 150);
  }, delay);
}

function play() {
  reaction.value = (reaction.value % 3) + 1;
  greet.value = true;
  blink.value = reaction.value === 1;
  clearTimeout(reopenTimer);
  clearTimeout(reactionTimer);
  reopenTimer = setTimeout(() => (blink.value = false), 180);
  reactionTimer = setTimeout(() => {
    greet.value = false;
    reaction.value = 0;
  }, 1500);
}

function updateMotionPreference() {
  reduced.value = preference.matches;
  if (reduced.value) {
    x.value = 0;
    y.value = 0;
    blink.value = false;
    clearTimeout(blinkTimer);
  } else {
    scheduleBlink(900);
  }
}

onMounted(() => {
  preference = matchMedia("(prefers-reduced-motion: reduce)");
  updateMotionPreference();
  preference.addEventListener("change", updateMotionPreference);
  window.addEventListener("pointermove", move, { passive: true });
});

onBeforeUnmount(() => {
  window.removeEventListener("pointermove", move);
  preference?.removeEventListener("change", updateMotionPreference);
  clearTimeout(blinkTimer);
  clearTimeout(reopenTimer);
  clearTimeout(reactionTimer);
});
</script>

<template>
  <button
    ref="mascot"
    class="mascot cat-mascot"
    :class="{
      small,
      greet,
      hovered,
      pawing: reaction === 1,
      purring: reaction === 2,
      celebrating: reaction === 3,
    }"
    @click="play"
    @pointerenter="hovered = true"
    @pointerleave="hovered = false"
    @focus="hovered = true"
    @blur="hovered = false"
    aria-label="和小护打个招呼"
    title="点点炫彩小猫，看看三种回应"
  >
    <svg
      viewBox="0 0 360 310"
      role="img"
      aria-label="炫彩小猫小护，会动耳朵、眨眼、追随鼠标并回应点击"
    >
      <defs>
        <linearGradient :id="`${uid}-prism`" x1=".05" y1=".05" x2=".95" y2=".9">
          <stop stop-color="#95eaff" />
          <stop offset=".22" stop-color="#c6b7ff" />
          <stop offset=".43" stop-color="#ffb8e7" />
          <stop offset=".62" stop-color="#ffe7a1" />
          <stop offset=".8" stop-color="#8ff0e2" />
          <stop offset="1" stop-color="#9f96ff" />
        </linearGradient>
        <linearGradient :id="`${uid}-pearl`" x1=".15" y1="0" x2=".8" y2="1">
          <stop stop-color="#ffffff" stop-opacity=".92" />
          <stop offset=".38" stop-color="#f2eaff" stop-opacity=".45" />
          <stop offset=".72" stop-color="#9edcff" stop-opacity=".2" />
          <stop offset="1" stop-color="#6a55d8" stop-opacity=".34" />
        </linearGradient>
        <linearGradient :id="`${uid}-tail`" x1="0" y1="0" x2="1" y2="1">
          <stop stop-color="#8ef0eb" />
          <stop offset=".48" stop-color="#bf9cff" />
          <stop offset="1" stop-color="#ffb9df" />
        </linearGradient>
        <radialGradient :id="`${uid}-iris`" cx=".35" cy=".25">
          <stop stop-color="#40578c" />
          <stop offset=".55" stop-color="#222348" />
          <stop offset="1" stop-color="#151326" />
        </radialGradient>
        <radialGradient :id="`${uid}-glow`">
          <stop stop-color="#fff" stop-opacity=".85" />
          <stop offset=".5" stop-color="#c9bfff" stop-opacity=".35" />
          <stop offset="1" stop-color="#6e6fe8" stop-opacity="0" />
        </radialGradient>
        <filter
          :id="`${uid}-blur`"
          x="-50%"
          y="-100%"
          width="200%"
          height="300%"
        >
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <filter
          :id="`${uid}-soft-glow`"
          x="-40%"
          y="-40%"
          width="180%"
          height="180%"
        >
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <ellipse
        cx="180"
        cy="286"
        rx="84"
        ry="10"
        fill="#5c65bd"
        opacity=".18"
        :filter="paint('blur')"
      />
      <g class="cat-aura">
        <ellipse
          cx="180"
          cy="165"
          rx="132"
          ry="115"
          fill="none"
          stroke="#91eaff"
          stroke-width="2"
        />
        <ellipse
          cx="180"
          cy="165"
          rx="145"
          ry="125"
          fill="none"
          stroke="#d2a6ff"
          stroke-width="2"
          stroke-dasharray="4 12"
        />
      </g>

      <g class="mascot-body cat-body">
        <g class="cat-pose" :style="{ transform: `rotate(${x * 0.42}deg)` }">
          <path
            class="cat-tail"
            d="M224 224C280 224 299 192 283 170C270 153 252 167 263 180"
            fill="none"
            :stroke="paint('tail')"
            stroke-width="19"
            stroke-linecap="round"
          />

          <path
            class="cat-torso"
            d="M137 181C119 204 112 242 121 273Q125 286 143 286H217Q235 286 239 273C248 242 241 204 223 181Z"
            :fill="paint('prism')"
            stroke="#6254b8"
            stroke-width="3"
          />
          <path
            d="M151 194C136 220 135 255 142 274M211 194C226 221 225 255 218 274"
            fill="none"
            stroke="#ffffff"
            stroke-width="5"
            stroke-linecap="round"
            opacity=".46"
          />

          <g class="cat-head">
            <g class="cat-ear cat-ear-left">
              <path
                d="M109 92L125 31Q128 20 137 29L170 66Z"
                :fill="paint('prism')"
                stroke="#6254b8"
                stroke-width="3"
                stroke-linejoin="round"
              />
              <path
                d="M121 77L130 43Q132 38 138 44L155 65Z"
                fill="#ffb6dd"
                opacity=".55"
              />
            </g>
            <g class="cat-ear cat-ear-right">
              <path
                d="M190 66L224 29Q233 20 236 32L251 93Z"
                :fill="paint('prism')"
                stroke="#6254b8"
                stroke-width="3"
                stroke-linejoin="round"
              />
              <path
                d="M205 65L224 43Q229 38 231 46L240 78Z"
                fill="#9ce6f1"
                opacity=".62"
              />
            </g>

            <path
              class="cat-face"
              d="M107 78C127 58 154 52 180 53C207 52 234 58 253 79C271 99 271 145 259 169C246 194 218 207 180 207C142 207 114 194 101 169C89 145 90 99 107 78Z"
              :fill="paint('prism')"
              stroke="#6254b8"
              stroke-width="3"
            />
            <path
              d="M111 83C137 62 165 60 188 61C151 75 124 97 108 128Q101 105 111 83Z"
              fill="#fff"
              opacity=".48"
            />
            <path
              class="prism-sheen"
              d="M118 160C137 119 170 91 224 78C248 96 257 124 250 151C239 186 208 198 177 198C150 198 129 185 118 160Z"
              :fill="paint('pearl')"
            />
            <ellipse
              cx="132"
              cy="168"
              rx="14"
              ry="8"
              fill="#ff99c8"
              opacity=".48"
            />
            <ellipse
              cx="228"
              cy="168"
              rx="14"
              ry="8"
              fill="#ff99c8"
              opacity=".48"
            />

            <g v-if="!blink && mood !== 'sleep'" class="eyes">
              <g :transform="`translate(${x} ${y})`">
                <ellipse
                  cx="145"
                  cy="135"
                  rx="13"
                  ry="18"
                  :fill="paint('iris')"
                />
                <ellipse
                  cx="215"
                  cy="135"
                  rx="13"
                  ry="18"
                  :fill="paint('iris')"
                />
                <ellipse cx="141" cy="128" rx="4.5" ry="6" fill="white" />
                <ellipse cx="211" cy="128" rx="4.5" ry="6" fill="white" />
                <circle cx="150" cy="144" r="2.5" fill="#a5efff" />
                <circle cx="220" cy="144" r="2.5" fill="#ffc4ed" />
              </g>
            </g>
            <g
              v-else
              class="closed-eyes"
              fill="none"
              stroke="#41375f"
              stroke-width="4"
              stroke-linecap="round"
            >
              <path d="M132 137Q145 148 158 137M202 137Q215 148 228 137" />
            </g>

            <path
              d="M175 155Q180 150 185 155Q180 161 175 155Z"
              fill="#5d4872"
            />
            <g
              class="cat-mouth"
              fill="none"
              stroke="#504166"
              stroke-width="3"
              stroke-linecap="round"
            >
              <path d="M180 160Q173 170 164 165M180 160Q187 170 196 165" />
            </g>
            <g
              class="whiskers"
              fill="none"
              stroke="#7b6a9a"
              stroke-width="2"
              stroke-linecap="round"
              opacity=".75"
            >
              <path
                d="M125 157L92 151M126 165L91 170M235 157L268 151M234 165L269 170"
              />
            </g>
          </g>

          <g class="cat-paw cat-paw-left">
            <path
              d="M137 221Q111 218 104 239"
              fill="none"
              :stroke="paint('tail')"
              stroke-width="15"
              stroke-linecap="round"
            />
            <ellipse
              cx="103"
              cy="243"
              rx="14"
              ry="13"
              :fill="paint('prism')"
              stroke="#6254b8"
              stroke-width="2"
            />
            <path
              d="M97 240V246M103 238V245M109 240V246"
              stroke="#fff"
              stroke-width="2"
              stroke-linecap="round"
              opacity=".75"
            />
          </g>
          <g class="cat-paw cat-paw-right">
            <path
              d="M223 219Q248 209 255 187"
              fill="none"
              :stroke="paint('tail')"
              stroke-width="15"
              stroke-linecap="round"
            />
            <ellipse
              cx="257"
              cy="181"
              rx="14"
              ry="13"
              :fill="paint('prism')"
              stroke="#6254b8"
              stroke-width="2"
            />
            <path
              d="M251 179V185M257 176V183M263 178V184"
              stroke="#fff"
              stroke-width="2"
              stroke-linecap="round"
              opacity=".75"
            />
          </g>

          <g class="cat-feet">
            <ellipse
              cx="148"
              cy="279"
              rx="24"
              ry="10"
              :fill="paint('tail')"
              stroke="#6254b8"
              stroke-width="2"
            />
            <ellipse
              cx="212"
              cy="279"
              rx="24"
              ry="10"
              :fill="paint('tail')"
              stroke="#6254b8"
              stroke-width="2"
            />
            <path
              d="M132 278H160M200 278H228"
              stroke="#fff"
              stroke-width="3"
              stroke-linecap="round"
              opacity=".65"
            />
          </g>

          <g class="cat-reactions" :filter="paint('soft-glow')">
            <path
              class="reaction-heart"
              d="M284 112C276 102 260 110 266 123L284 140L302 123C308 110 292 102 284 112Z"
              fill="#ff95cf"
            />
            <path
              class="reaction-star"
              d="M75 99L80 111L93 116L80 121L75 134L70 121L57 116L70 111Z"
              fill="#87e9ff"
            />
            <circle
              class="reaction-orb orb-one"
              cx="298"
              cy="178"
              r="5"
              fill="#ffe187"
            />
            <circle
              class="reaction-orb orb-two"
              cx="67"
              cy="184"
              r="4"
              fill="#c9a8ff"
            />
          </g>
        </g>
      </g>
    </svg>
  </button>
</template>

<style scoped>
.cat-pose {
  transform-origin: 180px 170px;
  transition: transform 0.34s ease-out;
}
.cat-head {
  transform-origin: 180px 174px;
}
.cat-ear {
  transform-box: fill-box;
  transition: transform 0.22s ease;
}
.cat-ear-left {
  transform-origin: 75% 90%;
  animation: listen-left 5.2s ease-in-out infinite;
}
.cat-ear-right {
  transform-origin: 25% 90%;
  animation: listen-right 6.1s 0.8s ease-in-out infinite;
}
.cat-tail {
  transform-origin: 226px 223px;
  animation: tail-idle 3.8s ease-in-out infinite;
}
.cat-paw-right {
  transform-origin: 224px 220px;
}
.cat-paw-left {
  transform-origin: 137px 221px;
}
.cat-mascot.hovered .cat-ear-left {
  transform: rotate(-8deg);
}
.cat-mascot.hovered .cat-ear-right {
  transform: rotate(8deg);
}
.cat-mascot.hovered .cat-tail,
.cat-mascot.greet .cat-tail {
  animation: tail-happy 0.48s ease-in-out 4 alternate;
}
.cat-mascot.pawing .cat-paw-right {
  animation: paw-wave 0.28s ease-in-out 4 alternate;
}
.cat-mascot.purring .cat-body {
  animation: cat-purr 0.12s linear 9 alternate !important;
}
.cat-mascot.purring .cat-face {
  filter: drop-shadow(0 0 8px #ffb7ea);
}
.cat-aura {
  opacity: 0;
  transform-origin: 180px 165px;
}
.cat-mascot.celebrating .cat-aura {
  animation: rainbow-aura 1.5s ease-out;
}
.cat-mascot.celebrating .cat-paw-left {
  animation: paws-up-left 0.45s ease-in-out 2 alternate;
}
.cat-mascot.celebrating .cat-paw-right {
  animation: paws-up-right 0.45s ease-in-out 2 alternate;
}
.prism-sheen {
  animation: pearl-shimmer 4.2s ease-in-out infinite;
}
.cat-reactions > * {
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
}
.pawing .reaction-heart {
  animation: reaction-pop 1.15s ease-out;
}
.purring .reaction-orb {
  animation: reaction-pop 1.05s ease-out;
}
.purring .orb-two {
  animation-delay: 0.12s;
}
.celebrating .reaction-star,
.celebrating .reaction-heart,
.celebrating .reaction-orb {
  animation: reaction-pop 1.2s ease-out;
}
.celebrating .reaction-heart {
  animation-delay: 0.08s;
}
@keyframes listen-left {
  0%,
  83%,
  100% {
    transform: rotate(0);
  }
  87% {
    transform: rotate(-7deg);
  }
  91% {
    transform: rotate(3deg);
  }
}
@keyframes listen-right {
  0%,
  86%,
  100% {
    transform: rotate(0);
  }
  90% {
    transform: rotate(7deg);
  }
  94% {
    transform: rotate(-3deg);
  }
}
@keyframes tail-idle {
  0%,
  100% {
    transform: rotate(-3deg);
  }
  50% {
    transform: rotate(5deg);
  }
}
@keyframes tail-happy {
  to {
    transform: rotate(15deg);
  }
}
@keyframes paw-wave {
  to {
    transform: rotate(-28deg) translateY(-3px);
  }
}
@keyframes cat-purr {
  to {
    transform: translateX(1.5px) rotate(0.4deg);
  }
}
@keyframes rainbow-aura {
  0% {
    opacity: 0;
    transform: scale(0.68) rotate(0);
  }
  30% {
    opacity: 0.8;
  }
  100% {
    opacity: 0;
    transform: scale(1.1) rotate(35deg);
  }
}
@keyframes paws-up-left {
  to {
    transform: rotate(26deg) translateY(-4px);
  }
}
@keyframes paws-up-right {
  to {
    transform: rotate(-26deg) translateY(-4px);
  }
}
@keyframes pearl-shimmer {
  0%,
  100% {
    opacity: 0.58;
  }
  50% {
    opacity: 0.92;
    filter: hue-rotate(24deg);
  }
}
@keyframes reaction-pop {
  0% {
    opacity: 0;
    transform: translateY(8px) scale(0.45) rotate(-12deg);
  }
  28% {
    opacity: 1;
    transform: translateY(0) scale(1.08) rotate(3deg);
  }
  100% {
    opacity: 0;
    transform: translateY(-17px) scale(0.9) rotate(9deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .cat-pose,
  .cat-ear,
  .cat-tail,
  .prism-sheen {
    transform: none !important;
    animation: none !important;
  }
  .cat-mascot.celebrating .cat-aura {
    opacity: 0.34;
  }
}
</style>
