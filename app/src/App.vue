<script setup lang="ts">
import { CircleAlert, LoaderCircle } from '@lucide/vue'
import { onBeforeUnmount, onMounted } from 'vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import EditorPanel from './components/EditorPanel.vue'
import EmptyState from './components/EmptyState.vue'
import EntryList from './components/EntryList.vue'
import FileDialog from './components/FileDialog.vue'
import PasswordDialog from './components/PasswordDialog.vue'
import PdfViewer from './components/PdfViewer.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import TexImportDialog from './components/TexImportDialog.vue'
import ToastStack from './components/ToastStack.vue'
import TopBar from './components/TopBar.vue'
import { onAppFileDrop, pickFile } from './platform'
import { openPath, removeEntry, saveConfig, startApp, store } from './store'

let stopDrop = () => {}

function retry() {
  store.loadError = ''
  startApp().catch((e) => (store.loadError = String(e)))
}

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
}

async function onKey(e: KeyboardEvent) {
  const mod = e.ctrlKey || e.metaKey
  if (mod && e.key.toLowerCase() === 's') {
    e.preventDefault()
    const path = !e.shiftKey && store.configPath ? store.configPath : await pickFile('config', 'save', store.configPath ?? undefined)
    if (path) await saveConfig(path)
  } else if (mod && e.key.toLowerCase() === 'o') {
    e.preventDefault()
    const path = await pickFile('pdf')
    if (path) await openPath(path)
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && store.selected && !typing(e.target)) {
    e.preventDefault()
    removeEntry(store.selected)
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  stopDrop = await onAppFileDrop((paths) => paths[0] && openPath(paths[0]))
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  stopDrop()
})
</script>

<template>
  <div v-if="store.ready" class="flex h-full flex-col">
    <TopBar />
    <div class="flex min-h-0 flex-1">
      <aside class="flex w-72 shrink-0 flex-col border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <EntryList />
      </aside>
      <main class="relative min-w-0 flex-1 bg-zinc-200/70 dark:bg-zinc-950">
        <PdfViewer v-if="store.pdf" />
        <EmptyState v-else />
      </main>
      <aside class="flex w-[22rem] shrink-0 flex-col border-l border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <EditorPanel />
      </aside>
    </div>
  </div>

  <div v-else class="grid h-full place-items-center p-6">
    <div v-if="store.loadError" class="card max-w-lg p-6">
      <div class="flex items-start gap-3">
        <CircleAlert class="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
        <div class="min-w-0">
          <h1 class="font-semibold">{{ $t('app.backendDown') }}</h1>
          <p class="mt-1 text-sm break-words whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">{{ store.loadError }}</p>
          <button class="btn-primary mt-4" @click="retry">
            {{ $t('app.retry') }}
          </button>
        </div>
      </div>
    </div>
    <div v-else class="flex items-center gap-3 text-sm text-zinc-500">
      <LoaderCircle class="h-5 w-5 animate-spin text-indigo-500" /> {{ $t('app.starting') }}
    </div>
  </div>

  <FileDialog />
  <TexImportDialog />
  <SettingsDialog />
  <PasswordDialog />
  <ToastStack />
  <ConfirmDialog />
</template>
