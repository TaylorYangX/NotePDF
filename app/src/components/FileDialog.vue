<script setup lang="ts">
import { ArrowUp, File, FileCode, FileText, Folder, HardDrive, House, LoaderCircle, Monitor } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type FsEntry, type FsListing } from '../api'
import { EXTENSIONS } from '../platform'
import { store } from '../store'
import ModalDialog from './ModalDialog.vue'

// The browser can't hand out file paths, so the backend lists folders instead (desktop app: native dialog).
const { t } = useI18n()
const listing = ref<FsListing | null>(null)
const location = ref('')
const fileName = ref('')
const chosen = ref<string | null>(null)
const error = ref('')
const loading = ref(false)
const nameInput = ref<HTMLInputElement>()
let edited = false // the user typed in the path box: a folder load still in flight mustn't overwrite it

const req = computed(() => store.fileRequest)
const title = computed(() => (req.value ? t(`files.${req.value.mode}_${req.value.kind}`) : ''))
const exts = computed(() => (req.value ? EXTENSIONS[req.value.kind] : []))

const ROOT_ICONS: Record<string, unknown> = { home: House, windows_c: HardDrive, root: HardDrive }

function remembered(kind: string): string | null {
  try {
    return localStorage.getItem(`notepdf.dir.${kind}`)
  } catch {
    return null
  }
}
function remember(kind: string, dir: string) {
  try {
    localStorage.setItem(`notepdf.dir.${kind}`, dir)
  } catch {
    /* private window */
  }
}

function dirname(p: string): string {
  return p.replace(/\/[^/]*$/, '') || '/'
}

watch(req, async (r) => {
  if (!r) return
  error.value = ''
  chosen.value = null
  fileName.value = r.suggested ? r.suggested.split('/').pop() ?? '' : ''
  const start = r.suggested ? dirname(r.suggested) : remembered(r.kind) ?? (store.pdf ? dirname(store.pdf.path) : store.meta?.home ?? '')
  await navigate(start)
  if (r.mode === 'save') {
    await nextTick()
    nameInput.value?.focus()
    nameInput.value?.select()
  }
})

async function load(path: string) {
  loading.value = true
  try {
    listing.value = await api<FsListing>(`/api/fs?path=${encodeURIComponent(path)}&ext=${exts.value.join(',')}`)
    if (!edited) location.value = listing.value.path
    error.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    // A path that isn't there any more: fall back to home.
    if (!listing.value && path !== (store.meta?.home ?? '')) await navigate(store.meta?.home ?? '')
  } finally {
    loading.value = false
  }
}

function navigate(path: string) {
  edited = false
  location.value = path
  return load(path)
}

async function goTo(text: string) {
  if (!text.trim()) return
  try {
    const res = await api<{ path: string; exists: boolean; is_dir: boolean }>('/api/path/normalize', { method: 'POST', json: { path: text } })
    if (res.is_dir) return navigate(res.path)
    if (req.value?.mode === 'open' && res.exists) return finish(res.path)
    if (req.value?.mode === 'save') {
      fileName.value = res.path.split('/').pop() ?? ''
      return navigate(dirname(res.path))
    }
    error.value = t('files.notFound', { path: res.path })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function click(e: FsEntry) {
  if (e.kind === 'dir') return navigate(e.path)
  chosen.value = e.path
  if (req.value?.mode === 'save') fileName.value = e.name
}

function open(e: FsEntry) {
  if (e.kind === 'dir') return navigate(e.path)
  finish(e.path)
}

function confirm() {
  if (!req.value || !listing.value) return
  if (req.value.mode === 'open') {
    if (chosen.value) finish(chosen.value)
    return
  }
  let name = fileName.value.trim()
  if (!name) return
  if (!exts.value.some((x) => name.toLowerCase().endsWith(`.${x}`))) name += `.${exts.value[0]}`
  finish(name.startsWith('/') ? name : `${listing.value.path.replace(/\/$/, '')}/${name}`)
}

function finish(path: string | null) {
  const r = req.value
  if (!r) return
  if (path) remember(r.kind, dirname(path))
  store.fileRequest = null
  r.resolve(path)
}

function size(n: number | null): string {
  if (n === null) return ''
  return n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`
}

function date(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function fileIcon(name: string) {
  return name.toLowerCase().endsWith('.pdf') ? FileText : /\.(tex|ya?ml|json)$/i.test(name) ? FileCode : File
}
</script>

<template>
  <ModalDialog :open="!!req" :title="title" width="max-w-3xl" @close="finish(null)">
    <div class="flex h-[30rem]">
      <nav class="w-48 shrink-0 space-y-0.5 border-r border-zinc-200 p-2 dark:border-zinc-800">
        <button
          v-for="r in listing?.roots ?? []"
          :key="r.path"
          class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          :title="r.path"
          @click="navigate(r.path)"
        >
          <component :is="ROOT_ICONS[r.name] ?? Monitor" class="h-4 w-4 shrink-0 text-zinc-400" />
          <span class="truncate">{{ $t(`files.root_${r.name}`) }}</span>
        </button>
      </nav>
      <div class="flex min-w-0 flex-1 flex-col">
        <div class="flex items-center gap-1.5 border-b border-zinc-200 p-2 dark:border-zinc-800">
          <button class="btn-ghost p-1.5" :disabled="!listing?.parent" :title="$t('files.up')" @click="listing?.parent && navigate(listing.parent)"><ArrowUp class="h-4 w-4" /></button>
          <input v-model="location" class="input-sm mono flex-1" :placeholder="$t('files.pathPlaceholder')" @input="edited = true" @keydown.enter="goTo(location)" />
          <LoaderCircle v-if="loading" class="h-4 w-4 animate-spin text-indigo-500" />
        </div>
        <p v-if="error" class="border-b border-red-200 bg-red-50 px-3 py-1.5 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">{{ error }}</p>
        <ul class="min-h-0 flex-1 overflow-y-auto p-1">
          <li v-if="listing && !listing.entries.length" class="p-6 text-center text-sm text-zinc-500">{{ $t('files.empty', { ext: exts.join(', ') }) }}</li>
          <li
            v-for="e in listing?.entries ?? []"
            :key="e.path"
            :class="[
              'flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px]',
              chosen === e.path ? 'bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-100' : 'hover:bg-zinc-100 dark:hover:bg-zinc-800',
            ]"
            @click="click(e)"
            @dblclick="open(e)"
          >
            <Folder v-if="e.kind === 'dir'" class="h-4 w-4 shrink-0 text-sky-500" />
            <component :is="fileIcon(e.name)" v-else class="h-4 w-4 shrink-0 text-zinc-400" />
            <span class="min-w-0 flex-1 truncate">{{ e.name }}</span>
            <span class="w-16 shrink-0 text-right text-[11px] text-zinc-400 tabular-nums">{{ size(e.size) }}</span>
            <span class="w-24 shrink-0 text-right text-[11px] text-zinc-400">{{ date(e.mtime) }}</span>
          </li>
        </ul>
        <div v-if="req?.mode === 'save'" class="flex items-center gap-2 border-t border-zinc-200 p-2 dark:border-zinc-800">
          <span class="text-[13px] text-zinc-500">{{ $t('files.fileName') }}</span>
          <input ref="nameInput" v-model="fileName" class="input-sm flex-1" @keydown.enter="confirm" />
        </div>
      </div>
    </div>
    <template #footer>
      <span class="mr-auto text-[11px] text-zinc-400">{{ store.meta?.wsl ? $t('files.wslHint') : '' }}</span>
      <button class="btn-secondary" @click="finish(null)">{{ $t('common.cancel') }}</button>
      <button class="btn-primary" :disabled="req?.mode === 'open' ? !chosen : !fileName.trim()" @click="confirm">
        {{ req?.mode === 'save' ? $t('common.save') : $t('common.open') }}
      </button>
    </template>
  </ModalDialog>
</template>
