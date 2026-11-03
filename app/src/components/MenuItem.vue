<script setup lang="ts">
defineProps<{ disabled?: boolean; hint?: string }>()
defineEmits<{ click: [] }>()
</script>

<template>
  <button
    class="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[13px] text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-zinc-200 dark:hover:bg-zinc-800"
    :disabled="disabled"
    @click="$emit('click')"
  >
    <slot />
    <span v-if="hint" class="ml-auto pl-4 text-[11px] text-zinc-400">{{ hint }}</span>
  </button>
</template>
