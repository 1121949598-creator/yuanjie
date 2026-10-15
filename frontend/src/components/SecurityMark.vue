<script setup>
import { useId } from "vue";

defineProps({ size: { type: Number, default: 32 } });
const uid = useId();
</script>

<template>
  <svg
    class="security-mark"
    :width="size"
    :height="size"
    viewBox="0 0 64 72"
    fill="none"
    role="img"
    aria-label="源界 安全守护标识"
  >
    <defs>
      <linearGradient
        :id="`${uid}-mark`"
        x1="8"
        y1="5"
        x2="57"
        y2="67"
        gradientUnits="userSpaceOnUse"
      >
        <stop stop-color="#6380ef" />
        <stop offset=".5" stop-color="#5269d9" />
        <stop offset="1" stop-color="#43b9d6" />
      </linearGradient>
    </defs>
    <g
      :stroke="`url(#${uid}-mark)`"
      stroke-width="4.3"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M29 7L12 15V31C12 47 19 58 29 64" />
      <path d="M35 7L52 15V31C52 47 45 58 35 64" />
      <path d="M12 31H23M41 31H52" />
      <path d="M32 12V25" />
      <path d="M32 47V63" />
      <path
        d="M27 47H37L35 39C39 37 41 34 41 30C41 25 37 21 32 21C27 21 23 25 23 30C23 34 25 37 29 39Z"
      />
    </g>
    <g :fill="`url(#${uid}-mark)`">
      <circle cx="32" cy="4" r="3" />
      <circle cx="9" cy="31" r="3" />
      <circle cx="55" cy="31" r="3" />
      <circle cx="32" cy="68" r="3" />
    </g>
  </svg>
</template>
