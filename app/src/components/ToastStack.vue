<script setup lang="ts">
import { CircleAlert, CircleCheck, Info, X } from '@lucide/vue'
import { dismissToast, store } from '../store'
</script>

<template>
  <div class="pointer-events-none fixed right-4 bottom-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
    <TransitionGroup
      enter-from-class="translate-y-2 opacity-0"
      leave-to-class="opacity-0"
      enter-active-class="transition duration-200"
      leave-active-class="transition duration-200"
    >
      <div v-for="t in store.toasts" :key="t.id" class="card pointer-events-auto px-3.5 py-3 text-sm shadow-lg">
        <div class="flex items-start gap-2.5">
          <CircleCheck v-if="t.kind === 'success'" class="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
          <CircleAlert v-else-if="t.kind === 'error'" class="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <Info v-else class="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
          <span class="min-w-0 flex-1 break-words">{{ t.message }}</span>
          <button class="-mt-0.5 -mr-1 p-0.5 text-zinc-400 hover:text-zinc-700" :aria-label="$t('common.close')" @click="dismissToast(t.id)"><X class="h-3.5 w-3.5" /></button>
        </div>
        <div v-if="t.actions?.length" class="mt-2 flex justify-end gap-1.5">
          <button v-for="a in t.actions" :key="a.label" class="btn-secondary btn-sm" @click="a.run(); dismissToast(t.id)">{{ a.label }}</button>
        </div>
      </div>
    </TransitionGroup>
  </div>
</template>
