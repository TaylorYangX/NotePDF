<script setup lang="ts">
import { X } from '@lucide/vue'
import { onBeforeUnmount, onMounted } from 'vue'

const props = defineProps<{ open: boolean; title: string; subtitle?: string; width?: string }>()
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (props.open && e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Transition enter-from-class="opacity-0" leave-to-class="opacity-0" enter-active-class="transition duration-150" leave-active-class="transition duration-100">
    <div v-if="open" class="fixed inset-0 z-40 grid place-items-center bg-zinc-950/40 p-4" @mousedown.self="emit('close')">
      <div :class="['card flex max-h-[min(88vh,52rem)] w-full flex-col shadow-2xl', width ?? 'max-w-xl']">
        <header class="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-3.5 dark:border-zinc-800">
          <div class="min-w-0">
            <h2 class="truncate text-[15px] font-semibold">{{ title }}</h2>
            <p v-if="subtitle" class="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{{ subtitle }}</p>
          </div>
          <button class="btn-ghost -mr-2 p-1.5" :aria-label="$t('common.close')" @click="emit('close')"><X class="h-4 w-4" /></button>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto"><slot /></div>
        <footer v-if="$slots.footer" class="flex items-center justify-end gap-2 border-t border-zinc-200 px-5 py-3 dark:border-zinc-800"><slot name="footer" /></footer>
      </div>
    </div>
  </Transition>
</template>
