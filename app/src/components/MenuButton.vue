<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps<{ align?: 'left' | 'right'; buttonClass?: string; label?: string }>()
const open = ref(false)
const root = ref<HTMLElement>()

function outside(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('mousedown', outside))
onBeforeUnmount(() => document.removeEventListener('mousedown', outside))
</script>

<template>
  <div ref="root" class="relative">
    <button :class="buttonClass ?? 'btn-secondary'" :aria-label="label" :aria-expanded="open" @click="open = !open">
      <slot name="button" />
    </button>
    <Transition enter-from-class="opacity-0 -translate-y-1" leave-to-class="opacity-0" enter-active-class="transition duration-100" leave-active-class="transition duration-75">
      <div
        v-if="open"
        :class="[
          'card absolute top-full z-30 mt-1 min-w-56 overflow-hidden py-1 shadow-lg',
          align === 'right' ? 'right-0' : 'left-0',
        ]"
        @click="open = false"
      >
        <slot />
      </div>
    </Transition>
  </div>
</template>
