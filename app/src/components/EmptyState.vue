<script setup lang="ts">
import { Clock, FileCode, FileText, FolderOpen, Highlighter, LoaderCircle } from '@lucide/vue'
import { computed } from 'vue'
import { pickFile } from '../platform'
import { openPath, store } from '../store'

const recent = computed(() => store.settings.recent.slice(0, 6))
const kindIcon = { pdf: FileText, config: FileCode, tex: FileCode }

async function open(kind: 'pdf' | 'config') {
  const path = await pickFile(kind)
  if (path) await openPath(path, kind)
}

function importTex() {
  store.texDialog = store.config.tex_source ? { ...store.config.tex_source } : { main: '', markers: [{ color: 'revcolor' }] }
}
</script>

<template>
  <div class="absolute inset-0 overflow-y-auto">
    <div class="mx-auto flex min-h-full max-w-2xl flex-col justify-center px-8 py-10">
      <div class="mb-6 flex items-center gap-3">
        <div class="grid h-11 w-11 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm"><Highlighter class="h-6 w-6" /></div>
        <div>
          <h1 class="text-lg font-semibold">{{ $t('empty.title') }}</h1>
          <p class="text-sm text-zinc-500 dark:text-zinc-400">{{ $t('empty.subtitle') }}</p>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3">
        <button class="card group flex flex-col items-start gap-2 p-4 text-left transition hover:border-indigo-400 hover:shadow-md" :disabled="store.opening" @click="open('pdf')">
          <LoaderCircle v-if="store.opening" class="h-5 w-5 animate-spin text-indigo-500" />
          <FolderOpen v-else class="h-5 w-5 text-indigo-500" />
          <span class="font-medium">{{ $t('top.openPdf') }}</span>
          <span class="text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{{ $t('empty.pdfHint') }}</span>
        </button>
        <button class="card flex flex-col items-start gap-2 p-4 text-left transition hover:border-indigo-400 hover:shadow-md" @click="open('config')">
          <FileCode class="h-5 w-5 text-emerald-500" />
          <span class="font-medium">{{ $t('top.openConfig') }}</span>
          <span class="text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{{ $t('empty.configHint') }}</span>
        </button>
        <button class="card flex flex-col items-start gap-2 p-4 text-left transition hover:border-indigo-400 hover:shadow-md" @click="importTex">
          <FileCode class="h-5 w-5 text-violet-500" />
          <span class="font-medium">{{ $t('top.importTex') }}</span>
          <span class="text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{{ $t('empty.texHint') }}</span>
        </button>
      </div>

      <div v-if="recent.length" class="mt-8">
        <h2 class="panel-title mb-2">{{ $t('top.recent') }}</h2>
        <ul class="card divide-y divide-zinc-200 overflow-hidden dark:divide-zinc-800">
          <li v-for="r in recent" :key="r.path">
            <button class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/60" @click="openPath(r.path, r.kind)">
              <component :is="kindIcon[r.kind]" class="h-4 w-4 shrink-0 text-zinc-400" />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-[13px] font-medium">{{ r.path.split('/').pop() }}</span>
                <span class="mono block truncate text-[11px] text-zinc-500">{{ r.path }}</span>
              </span>
              <Clock class="h-3.5 w-3.5 shrink-0 text-zinc-300" />
            </button>
          </li>
        </ul>
      </div>

      <ol class="mt-8 space-y-1.5 text-[13px] text-zinc-600 dark:text-zinc-400">
        <li v-for="n in 3" :key="n" class="flex gap-2">
          <span class="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-zinc-200 text-[11px] font-semibold dark:bg-zinc-800">{{ n }}</span>
          {{ $t(`empty.step${n}`) }}
        </li>
      </ol>
    </div>
  </div>
</template>
