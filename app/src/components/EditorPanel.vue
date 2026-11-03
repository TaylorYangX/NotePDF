<script setup lang="ts">
import { MousePointerClick } from '@lucide/vue'
import { computed } from 'vue'
import { selectedEntry, store } from '../store'
import DocumentPanel from './DocumentPanel.vue'
import EntryEditor from './EntryEditor.vue'

const entry = computed(() => selectedEntry())
</script>

<template>
  <div class="flex border-b border-zinc-200 px-2 dark:border-zinc-800">
    <button :class="store.rightTab === 'entry' ? 'tab-active' : 'tab'" @click="store.rightTab = 'entry'">{{ $t('editor.tabEntry') }}</button>
    <button :class="store.rightTab === 'document' ? 'tab-active' : 'tab'" @click="store.rightTab = 'document'">{{ $t('editor.tabDocument') }}</button>
  </div>
  <div class="min-h-0 flex-1 overflow-y-auto">
    <template v-if="store.rightTab === 'entry'">
      <EntryEditor v-if="entry" :key="entry._id" :entry="entry" />
      <div v-else class="px-6 py-10 text-center text-sm text-zinc-500">
        <MousePointerClick class="mx-auto mb-3 h-7 w-7 text-zinc-300 dark:text-zinc-600" />
        <p class="font-medium text-zinc-700 dark:text-zinc-300">{{ $t('editor.noneTitle') }}</p>
        <p class="mt-1.5 leading-relaxed">{{ $t('editor.noneHint') }}</p>
      </div>
    </template>
    <DocumentPanel v-else />
  </div>
</template>
