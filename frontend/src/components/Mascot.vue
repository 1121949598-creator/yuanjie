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
  const dy = event.clientY - box.top - box.height * 0.42;
  const distance = Math.hypot(dx, dy) || 1;
  const amount = Math.min(5.5, distance / 34);
  x.value = (dx / distance) * amount;
  y.value = (dy / distance) * amount;
}

function scheduleBlink(delay = 2700 + Math.random() * 2600) {
  clearTimeout(blinkTimer);
  if (reduced.value) return;
  blinkTimer = setTimeout(() => {
    blink.value = true;
    reopenTimer = setTimeout(() => {
      blink.value = false;
      scheduleBlink();
    }, 145);
  }, delay);
}

function play() {
  reaction.value = (reaction.value % 3) + 1;
  greet.value = true;
  blink.value = reaction.value === 2;
  clearTimeout(reopenTimer);
  clearTimeout(reactionTimer);
  reopenTimer = setTimeout(() => (blink.value = false), 190);
  reactionTimer = setTimeout(() => {
    greet.value = false;
    reaction.value = 0;
  }, 1600);
}

function updateMotionPreference() {
  reduced.value = preference.matches;
  if (reduced.value) {
    x.value = 0;
    y.value = 0;
    blink.value = false;
    clearTimeout(blinkTimer);
  } else {
    scheduleBlink(750);
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
    class="mascot cat-mascot pearl-cat"
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
    aria-label="和胖胖猫小护打个招呼"
    title="点点胖胖猫，看看三种回应"
  >
    <svg
      viewBox="0 0 360 310"
      role="img"
      aria-label="晶莹的胖胖卡通猫小护，会动耳朵、眨眼、追随鼠标并回应点击"
    >
      <defs>
        <linearGradient
          :id="`${uid}-pearl-face`"
          x1=".12"
          y1=".04"
          x2=".84"
          y2=".96"
        >
          <stop stop-color="#ffffff" stop-opacity=".88" />
          <stop offset=".34" stop-color="#eafaff" stop-opacity=".76" />
          <stop offset=".68" stop-color="#eee8ff" stop-opacity=".74" />
          <stop offset="1" stop-color="#f8e8f3" stop-opacity=".7" />
        </linearGradient>
        <linearGradient
          :id="`${uid}-pearl-body`"
          x1=".18"
          y1="0"
          x2=".76"
          y2="1"
        >
          <stop stop-color="#ffffff" stop-opacity=".84" />
          <stop offset=".42" stop-color="#e7f9ff" stop-opacity=".7" />
          <stop offset=".72" stop-color="#f2eaff" stop-opacity=".72" />
          <stop offset="1" stop-color="#e2f0ff" stop-opacity=".68" />
        </linearGradient>
        <linearGradient :id="`${uid}-ear`" x1=".1" y1="0" x2=".8" y2="1">
          <stop stop-color="#f9ddea" stop-opacity=".82" />
          <stop offset="1" stop-color="#d9d9f5" stop-opacity=".7" />
        </linearGradient>
        <linearGradient :id="`${uid}-tail`" x1="0" y1=".2" x2="1" y2=".8">
          <stop stop-color="#dffaff" stop-opacity=".84" />
          <stop offset=".48" stop-color="#eee6ff" stop-opacity=".78" />
          <stop offset="1" stop-color="#f5ddef" stop-opacity=".8" />
        </linearGradient>
        <linearGradient :id="`${uid}-mist`" x1="0" y1="0" x2="1" y2="1">
          <stop stop-color="#65dfe9" />
          <stop offset=".4" stop-color="#c5a4f3" />
          <stop offset=".7" stop-color="#f3a8d2" />
          <stop offset="1" stop-color="#ffe2a0" />
        </linearGradient>
        <linearGradient :id="`${uid}-rim`" x1=".08" y1="0" x2=".94" y2="1">
          <stop stop-color="#70cfe8" />
          <stop offset=".42" stop-color="#8795d8" />
          <stop offset=".72" stop-color="#cb9bd4" />
          <stop offset="1" stop-color="#7fc9df" />
        </linearGradient>
        <radialGradient :id="`${uid}-iris`" cx=".36" cy=".25">
          <stop stop-color="#5b78a5" />
          <stop offset=".45" stop-color="#293958" />
          <stop offset="1" stop-color="#182038" />
        </radialGradient>
        <radialGradient :id="`${uid}-blush`">
          <stop stop-color="#f6a9c9" stop-opacity=".48" />
          <stop offset="1" stop-color="#f6a9c9" stop-opacity="0" />
        </radialGradient>
        <filter
          :id="`${uid}-shadow`"
          x="-50%"
          y="-120%"
          width="200%"
          height="340%"
        >
          <feGaussianBlur stdDeviation="7" />
        </filter>
        <filter
          :id="`${uid}-soft-glow`"
          x="-60%"
          y="-60%"
          width="220%"
          height="220%"
        >
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient :id="`${uid}-opal`" cx=".64" cy=".72" r=".7">
          <stop stop-color="#f3acd8" stop-opacity=".38" />
          <stop offset=".46" stop-color="#cec5fb" stop-opacity=".23" />
          <stop offset=".78" stop-color="#97e4ed" stop-opacity=".18" />
          <stop offset="1" stop-color="#c6f3ff" stop-opacity="0" />
        </radialGradient>
        <mask
          :id="`${uid}-behind-face`"
          maskUnits="userSpaceOnUse"
          x="0"
          y="0"
          width="360"
          height="310"
        >
          <rect width="360" height="310" fill="white" />
          <path
            d="M180 79C146 77 117 89 107 114C103 126 102 131 98 143C90 164 104 184 129 195C144 203 161 207 180 207C199 207 216 203 231 195C256 184 270 164 262 143C258 131 257 126 253 114C243 89 214 77 180 79Z"
            fill="black"
            stroke="black"
            stroke-width="1"
          />
        </mask>
      </defs>

      <ellipse
        cx="180"
        cy="289"
        rx="82"
        ry="9"
        fill="#6675ad"
        opacity=".16"
        :filter="paint('shadow')"
      />
      <g class="cat-aura" fill="none" stroke-linecap="round">
        <path
          d="M57 185C60 82 129 33 224 55C306 74 326 187 272 251"
          stroke="#9adfe8"
          stroke-width="2"
        />
        <path
          d="M89 256C39 202 77 111 140 76"
          stroke="#d7bde8"
          stroke-width="2"
          stroke-dasharray="3 12"
        />
      </g>

      <g class="mascot-body cat-body">
        <g class="cat-pose" :style="{ transform: `rotate(${x * 0.34}deg)` }">
          <g class="cat-tail">
            <path
              d="M226 252C271 278 310 251 296 215C289 195 269 192 264 210"
              fill="none"
              stroke="#8a9bc7"
              stroke-opacity=".32"
              stroke-width="31"
              stroke-linecap="round"
            />
            <path
              d="M226 250C271 275 303 249 290 218C284 204 272 202 268 212"
              fill="none"
              :stroke="paint('tail')"
              stroke-width="26"
              stroke-linecap="round"
            />
            <path
              d="M239 251C266 263 286 251 288 233"
              fill="none"
              stroke="white"
              stroke-width="5"
              stroke-linecap="round"
              opacity=".62"
            />
          </g>

          <!-- Keep hidden body/ear edges out of the translucent face. -->
          <g :mask="paint('behind-face')">
            <path
              class="cat-torso"
              d="M136 179C111 191 93 224 96 254C98 283 133 298 180 298C227 298 262 283 264 254C267 224 249 191 224 179Z"
              :fill="paint('pearl-body')"
              :stroke="paint('rim')"
              stroke-width="2.2"
            />
            <ellipse
              cx="180"
              cy="246"
              rx="51"
              ry="43"
              fill="white"
              opacity=".36"
            />
            <ellipse
              class="chest-mist"
              cx="188"
              cy="240"
              rx="53"
              ry="45"
              :fill="paint('opal')"
            />
            <path
              d="M160 218Q169 225 180 218Q191 225 200 218"
              fill="none"
              stroke="#b8d2e2"
              stroke-opacity=".6"
              stroke-width="1.8"
              stroke-linecap="round"
            />
            <path
              d="M108 231Q102 253 120 270"
              fill="none"
              stroke="white"
              stroke-width="4"
              opacity=".72"
              stroke-linecap="round"
            />
            <g class="cat-ear cat-ear-left">
              <path
                d="M108 116C105 98 97 72 104 55Q107 48 114 52C130 60 142 75 151 90Z"
                :fill="paint('pearl-face')"
                :stroke="paint('rim')"
                stroke-width="2.2"
                stroke-linejoin="round"
              />
              <path
                d="M113 94Q106 72 110 61Q125 68 138 86Z"
                :fill="paint('ear')"
              />
              <path
                d="M105 67Q104 59 109 56"
                fill="none"
                stroke="white"
                stroke-width="3"
                stroke-linecap="round"
              />
            </g>
            <g class="cat-ear cat-ear-right">
              <path
                d="M209 90C218 75 230 60 246 52Q253 48 256 55C263 72 255 98 252 116Z"
                :fill="paint('pearl-face')"
                :stroke="paint('rim')"
                stroke-width="2.2"
                stroke-linejoin="round"
              />
              <path
                d="M222 86Q235 68 250 61Q254 72 247 94Z"
                :fill="paint('ear')"
              />
              <path
                d="M251 57Q256 64 253 75"
                fill="none"
                stroke="white"
                stroke-width="3"
                stroke-linecap="round"
              />
            </g>
          </g>

          <g class="cat-head">
            <path
              class="cat-face"
              d="M180 79C146 77 117 89 107 114C103 126 102 131 98 143C90 164 104 184 129 195C144 203 161 207 180 207C199 207 216 203 231 195C256 184 270 164 262 143C258 131 257 126 253 114C243 89 214 77 180 79Z"
              :fill="paint('pearl-face')"
              :stroke="paint('rim')"
              stroke-width="2.2"
            />
            <ellipse
              class="face-mist"
              cx="180"
              cy="148"
              rx="78"
              ry="56"
              :fill="paint('opal')"
            />
            <path
              d="M120 111C130 95 149 88 169 87"
              fill="none"
              stroke="white"
              stroke-width="5.5"
              opacity=".86"
              stroke-linecap="round"
            />
            <path
              d="M252 152Q252 176 231 184"
              fill="none"
              stroke="white"
              stroke-width="3"
              opacity=".65"
              stroke-linecap="round"
            />
            <ellipse cx="123" cy="166" rx="22" ry="14" :fill="paint('blush')" />
            <ellipse cx="237" cy="166" rx="22" ry="14" :fill="paint('blush')" />

            <g v-if="!blink && mood !== 'sleep'" class="eyes">
              <g :transform="`translate(${x * 0.7} ${y * 0.7})`">
                <ellipse
                  cx="149"
                  cy="146"
                  rx="12"
                  ry="15.5"
                  :fill="paint('iris')"
                />
                <ellipse
                  cx="211"
                  cy="146"
                  rx="12"
                  ry="15.5"
                  :fill="paint('iris')"
                />
                <ellipse cx="145.5" cy="141" rx="4.2" ry="5.2" fill="white" />
                <ellipse cx="207.5" cy="141" rx="4.2" ry="5.2" fill="white" />
                <ellipse
                  cx="153"
                  cy="153"
                  rx="3.1"
                  ry="2.3"
                  fill="#b4e9f2"
                  opacity=".9"
                />
                <ellipse
                  cx="215"
                  cy="153"
                  rx="3.1"
                  ry="2.3"
                  fill="#cfc7f3"
                  opacity=".9"
                />
              </g>
            </g>
            <g
              v-else
              class="closed-eyes"
              fill="none"
              stroke="#44516d"
              stroke-width="3.4"
              stroke-linecap="round"
            >
              <path d="M138 148Q149 158 160 148M200 148Q211 158 222 148" />
            </g>
            <path
              d="M176 164Q180 161 184 164Q184 166 180 168Q176 166 176 164Z"
              fill="#bb859f"
            />
            <g
              class="cat-mouth"
              fill="none"
              stroke="#626984"
              stroke-width="2.2"
              stroke-linecap="round"
            >
              <path
                d="M180 168C180 176 169 178 167 172M180 168C180 176 191 178 193 172"
              />
            </g>
            <g
              class="whiskers"
              fill="none"
              stroke="#96a0bb"
              stroke-width="1.5"
              stroke-linecap="round"
              opacity=".65"
            >
              <path
                d="M127 165L110 161M127 172L110 174M233 165L250 161M233 172L250 174"
              />
            </g>
          </g>

          <g class="cat-paw cat-paw-left">
            <ellipse
              cx="126"
              cy="231"
              rx="20"
              ry="24"
              transform="rotate(18 126 231)"
              :fill="paint('pearl-face')"
              :stroke="paint('rim')"
              stroke-width="2.3"
            />
            <path
              d="M115 229Q126 237 138 229"
              fill="none"
              stroke="#c8d6e8"
              stroke-width="2"
              stroke-linecap="round"
            />
            <circle cx="121" cy="226" r="2.2" fill="#e1b6ce" />
            <circle cx="128" cy="224" r="2.2" fill="#e1b6ce" />
            <circle cx="134" cy="226" r="2.2" fill="#e1b6ce" />
          </g>
          <g class="cat-paw cat-paw-right">
            <ellipse
              cx="234"
              cy="228"
              rx="20"
              ry="24"
              transform="rotate(-20 234 228)"
              :fill="paint('pearl-face')"
              :stroke="paint('rim')"
              stroke-width="2.3"
            />
            <path
              d="M222 226Q234 234 246 226"
              fill="none"
              stroke="#c8d6e8"
              stroke-width="2"
              stroke-linecap="round"
            />
            <circle cx="228" cy="223" r="2.2" fill="#e1b6ce" />
            <circle cx="235" cy="221" r="2.2" fill="#e1b6ce" />
            <circle cx="241" cy="223" r="2.2" fill="#e1b6ce" />
          </g>

          <g class="cat-feet">
            <path
              d="M119 272C122 256 145 253 160 264C168 271 163 286 151 290C134 296 116 287 119 272Z"
              :fill="paint('pearl-face')"
              :stroke="paint('rim')"
              stroke-width="2.4"
            />
            <path
              d="M241 272C238 256 215 253 200 264C192 271 197 286 209 290C226 296 244 287 241 272Z"
              :fill="paint('pearl-face')"
              :stroke="paint('rim')"
              stroke-width="2.4"
            />
            <path
              d="M131 276L130 284M140 275L140 285M229 276L230 284M220 275L220 285"
              stroke="#c2d0e2"
              stroke-width="2"
              stroke-linecap="round"
            />
          </g>

          <g class="cat-reactions" :filter="paint('soft-glow')">
            <path
              class="reaction-heart"
              d="M285 111C278 101 263 108 267 120L285 137L303 120C307 108 292 101 285 111Z"
              fill="#ef9dc8"
            />
            <path
              class="reaction-star"
              d="M73 104L78 115L90 120L78 125L73 137L68 125L56 120L68 115Z"
              fill="#8adbe8"
            />
            <path
              class="reaction-star star-two"
              d="M302 168L305 175L313 178L305 181L302 189L299 181L291 178L299 175Z"
              fill="#d6bce9"
            />
            <circle
              class="reaction-orb orb-one"
              cx="294"
              cy="205"
              r="5"
              fill="#f6d9a4"
            />
            <circle
              class="reaction-orb orb-two"
              cx="66"
              cy="190"
              r="4"
              fill="#b8cfeb"
            />
          </g>
        </g>
      </g>
    </svg>
  </button>
</template>

<style scoped>
.cat-pose {
  transform-origin: 180px 172px;
  transition: transform 0.34s ease-out;
}
.cat-head {
  transform-origin: 180px 178px;
}
.cat-ear {
  transform-box: fill-box;
  transition: transform 0.22s ease;
}
.cat-ear-left {
  transform-origin: 80% 92%;
  animation: ear-left 5.4s ease-in-out infinite;
}
.cat-ear-right {
  transform-origin: 20% 92%;
  animation: ear-right 6.3s 0.7s ease-in-out infinite;
}
.cat-tail {
  transform-origin: 231px 252px;
  animation: tail-idle 3.9s ease-in-out infinite;
}
.cat-paw-right {
  transform-origin: 226px 238px;
}
.cat-paw-left {
  transform-origin: 134px 240px;
}
.face-mist,
.chest-mist {
  animation: crystal-breathe 4.6s ease-in-out infinite;
}
.cat-mascot.hovered .cat-ear-left {
  transform: rotate(-7deg);
}
.cat-mascot.hovered .cat-ear-right {
  transform: rotate(7deg);
}
.cat-mascot.hovered .cat-brows {
  transform: translateY(-1px);
}
.cat-mascot.hovered .cat-tail,
.cat-mascot.greet .cat-tail {
  animation: tail-happy 0.45s ease-in-out 5 alternate;
}
.cat-mascot.pawing .cat-paw-right {
  animation: paw-wave 0.3s ease-in-out 4 alternate;
}
.cat-mascot.purring .cat-body {
  animation: cat-purr 0.12s linear 10 alternate !important;
}
.cat-mascot.purring .cat-mouth {
  transform-origin: 180px 165px;
  animation: smile-pop 0.42s ease-in-out 2 alternate;
}
.cat-aura {
  opacity: 0;
  transform-origin: 180px 170px;
}
.cat-mascot.celebrating .cat-aura {
  animation: pearl-aura 1.55s ease-out;
}
.cat-mascot.celebrating .cat-paw-left {
  animation: paws-up-left 0.42s ease-in-out 2 alternate;
}
.cat-mascot.celebrating .cat-paw-right {
  animation: paws-up-right 0.42s ease-in-out 2 alternate;
}
.cat-reactions > * {
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
}
.pawing .reaction-heart {
  animation: reaction-pop 1.2s ease-out;
}
.purring .reaction-orb {
  animation: reaction-pop 1.1s ease-out;
}
.purring .orb-two {
  animation-delay: 0.14s;
}
.celebrating .reaction-star,
.celebrating .reaction-heart,
.celebrating .reaction-orb {
  animation: reaction-pop 1.25s ease-out;
}
.celebrating .star-two {
  animation-delay: 0.1s;
}
@keyframes ear-left {
  0%,
  82%,
  100% {
    transform: rotate(0);
  }
  87% {
    transform: rotate(-8deg);
  }
  92% {
    transform: rotate(3deg);
  }
}
@keyframes ear-right {
  0%,
  85%,
  100% {
    transform: rotate(0);
  }
  90% {
    transform: rotate(8deg);
  }
  95% {
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
    transform: rotate(13deg) translateY(-2px);
  }
}
@keyframes paw-wave {
  to {
    transform: rotate(-31deg) translate(-3px, -9px);
  }
}
@keyframes cat-purr {
  to {
    transform: translateX(1.2px) rotate(0.35deg);
  }
}
@keyframes smile-pop {
  to {
    transform: scale(1.08);
  }
}
@keyframes crystal-breathe {
  0%,
  100% {
    opacity: 0.7;
  }
  50% {
    opacity: 1;
  }
}
@keyframes pearl-aura {
  0% {
    opacity: 0;
    transform: scale(0.72) rotate(-8deg);
  }
  28% {
    opacity: 0.65;
  }
  100% {
    opacity: 0;
    transform: scale(1.12) rotate(24deg);
  }
}
@keyframes paws-up-left {
  to {
    transform: rotate(22deg) translate(-4px, -7px);
  }
}
@keyframes paws-up-right {
  to {
    transform: rotate(-22deg) translate(4px, -7px);
  }
}
@keyframes reaction-pop {
  0% {
    opacity: 0;
    transform: translateY(7px) scale(0.45) rotate(-10deg);
  }
  28% {
    opacity: 1;
    transform: translateY(0) scale(1.06) rotate(2deg);
  }
  100% {
    opacity: 0;
    transform: translateY(-18px) scale(0.92) rotate(8deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .cat-pose,
  .cat-ear,
  .cat-tail,
  .face-mist,
  .chest-mist {
    transform: none !important;
    animation: none !important;
  }
  .cat-mascot.celebrating .cat-aura {
    opacity: 0.3;
  }
}
</style>
