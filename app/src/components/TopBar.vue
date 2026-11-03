<script setup lang="ts">
import {
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Clock,
  ExternalLink,
  FileCode,
  FilePlus,
  FileText,
  FolderOpen,
  Highlighter,
  LoaderCircle,
  Save,
  Scan,
  Settings,
  TriangleAlert,
  ZoomIn,
  ZoomOut,
} from '@lucide/vue'
import { computed } from 'vue'
import { pickFile } from '../platform'
import { applyPdf, newConfig, openExternal, openPath, previewCounts, saveConfig, store } from '../store'
import MenuButton from './MenuButton.vue'
import MenuItem from './MenuItem.vue'

const counts = computed(() => previewCounts())
const zoomLabel = computed(() => (store.zoom === 'fit' ? '' : `${Math.round(store.zoom * 100)}%`))
const configName = computed(() => store.configPath?.split('/').pop() ?? null)
const recent = computed(() => store.settings.recent.slice(0, 8))
const mod = navigator.platform.toLowerCase().includes('mac') ? '⌘' : 'Ctrl+'

async function open(kind: 'pdf' | 'config' | 'tex') {
  if (kind === 'tex') {
    store.texDialog = store.config.tex_source ? { ...store.config.tex_source } : { main: '', markers: [{ color: 'revcolor' }] }
    return
  }
  const path = await pickFile(kind)
  if (path) await openPath(path, kind)
}

async function save(as = false) {
  const path = !as && store.configPath ? store.configPath : await pickFile('config', 'save', store.configPath ?? suggestedConfig())
  if (path) await saveConfig(path)
}

function suggestedConfig(): string | undefined {
  return store.pdf ? store.pdf.path.replace(/\.pdf$/i, '.notepdf.yaml') : undefined
}

async function saveAs() {
  const suggested = store.config.output ?? store.pdf?.path.replace(/\.pdf$/i, '.annotated.pdf')
  const path = await pickFile('pdf', 'save', suggested)
  if (path) await applyPdf(path)
}

function zoom(step: number) {
  const current = store.zoom === 'fit' ? currentFitScale() : store.zoom
  const next = Math.min(4, Math.max(0.25, Math.round((current + step) * 4) / 4))
  store.zoom = next
}

function currentFitScale(): number {
  return Number(document.querySelector<HTMLElement>('[data-fit-scale]')?.dataset.fitScale ?? 1)
}

function shortPath(p: string): string {
  const parts = p.split('/')
  return parts.length > 3 ? `…/${parts.slice(-2).join('/')}` : p
}
</script>

<template>
  <header class="flex h-14 shrink-0 items-center gap-2 border-b border-zinc-200 bg-white px-3 dark:border-zinc-800 dark:bg-zinc-900">
    <div class="mr-2 flex min-w-0 items-center gap-2">
      <div class="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-indigo-600 text-white"><Highlighter class="h-4.5 w-4.5" /></div>
      <div class="min-w-0 leading-tight">
        <div class="flex items-center gap-1.5 text-sm font-semibold">
          NotePDF
          <span v-if="store.dirty && store.config.annotations.length" class="h-1.5 w-1.5 rounded-full bg-amber-500" :title="$t('top.unsaved')" />
        </div>
        <div class="max-w-64 truncate text-[11px] text-zinc-500 dark:text-zinc-400" :title="store.pdf?.path">
          {{ store.pdf?.name ?? $t('top.noPdf') }}<template v-if="configName"> · {{ configName }}</template>
        </div>
      </div>
    </div>

    <MenuButton>
      <template #button><FolderOpen class="h-4 w-4" />{{ $t('top.open') }}<ChevronDown class="h-3.5 w-3.5 opacity-60" /></template>
      <MenuItem :hint="`${mod}O`" @click="open('pdf')"><FileText class="h-4 w-4 text-zinc-400" />{{ $t('top.openPdf') }}</MenuItem>
      <MenuItem @click="open('config')"><FileCode class="h-4 w-4 text-zinc-400" />{{ $t('top.openConfig') }}</MenuItem>
      <MenuItem @click="newConfig()"><FilePlus class="h-4 w-4 text-zinc-400" />{{ $t('top.newConfig') }}</MenuItem>
      <template v-if="recent.length">
        <div class="mt-1 border-t border-zinc-200 px-3 pt-2 pb-1 panel-title dark:border-zinc-800">{{ $t('top.recent') }}</div>
        <MenuItem v-for="r in recent" :key="r.path" @click="openPath(r.path, r.kind)">
          <Clock class="h-3.5 w-3.5 shrink-0 text-zinc-400" />
          <span class="truncate" :title="r.path">{{ shortPath(r.path) }}</span>
        </MenuItem>
      </template>
    </MenuButton>

    <button class="btn-secondary" @click="open('tex')"><FileCode class="h-4 w-4" />{{ $t('top.importTex') }}</button>

    <MenuButton>
      <template #button><Save class="h-4 w-4" />{{ $t('top.saveConfig') }}<ChevronDown class="h-3.5 w-3.5 opacity-60" /></template>
      <MenuItem :hint="`${mod}S`" @click="save()">{{ $t('top.saveConfig') }}</MenuItem>
      <MenuItem :hint="`${mod}⇧S`" @click="save(true)">{{ $t('top.saveConfigAs') }}</MenuItem>
    </MenuButton>

    <div class="flex-1" />

    <div v-if="store.pdf" class="flex items-center gap-3 text-xs">
      <LoaderCircle v-if="store.previewing" class="h-3.5 w-3.5 animate-spin text-indigo-500" />
      <button class="flex items-center gap-1 text-emerald-600 dark:text-emerald-400" :title="$t('status.found')" @click="store.filter = 'all'">
        <CircleCheck class="h-3.5 w-3.5" />{{ counts.found }}
      </button>
      <button v-if="counts.warning" class="flex items-center gap-1 text-amber-600 dark:text-amber-400" :title="$t('status.warning')" @click="store.filter = 'warning'">
        <TriangleAlert class="h-3.5 w-3.5" />{{ counts.warning }}
      </button>
      <button v-if="counts.missing + counts.invalid" class="flex items-center gap-1 text-red-600 dark:text-red-400" :title="$t('status.missing')" @click="store.filter = 'missing'">
        <CircleAlert class="h-3.5 w-3.5" />{{ counts.missing + counts.invalid }}
      </button>
    </div>

    <div v-if="store.pdf" class="ml-2 flex items-center rounded-lg border border-zinc-300 dark:border-zinc-700">
      <button class="btn-ghost rounded-r-none px-2 py-1.5" :title="$t('top.zoomOut')" @click="zoom(-0.25)"><ZoomOut class="h-4 w-4" /></button>
      <button
        :class="['px-2 py-1.5 text-xs tabular-nums', store.zoom === 'fit' ? 'text-indigo-600 dark:text-indigo-400' : 'text-zinc-600 dark:text-zinc-300']"
        :title="$t('top.fit')"
        @click="store.zoom = 'fit'"
      >
        <Scan v-if="store.zoom === 'fit'" class="h-4 w-4" /><span v-else class="inline-block w-10">{{ zoomLabel }}</span>
      </button>
      <button class="btn-ghost rounded-l-none px-2 py-1.5" :title="$t('top.zoomIn')" @click="zoom(0.25)"><ZoomIn class="h-4 w-4" /></button>
    </div>

    <div class="ml-2 flex">
      <button class="btn-primary rounded-r-none" :disabled="!store.pdf || store.applying" @click="applyPdf()">
        <LoaderCircle v-if="store.applying" class="h-4 w-4 animate-spin" /><Highlighter v-else class="h-4 w-4" />{{ $t('top.savePdf') }}
      </button>
      <MenuButton align="right" button-class="btn-primary rounded-l-none border-l border-indigo-500 px-2" :label="$t('top.more')">
        <template #button><ChevronDown class="h-4 w-4" /></template>
        <MenuItem :disabled="!store.pdf" @click="saveAs()">{{ $t('top.savePdfAs') }}</MenuItem>
        <MenuItem :disabled="!store.lastOutput" @click="store.lastOutput && openExternal(store.lastOutput)">
          <ExternalLink class="h-4 w-4 text-zinc-400" />{{ $t('apply.open') }}
        </MenuItem>
        <MenuItem :disabled="!store.lastOutput" @click="store.lastOutput && openExternal(store.lastOutput, true)">
          <FolderOpen class="h-4 w-4 text-zinc-400" />{{ $t('apply.reveal') }}
        </MenuItem>
      </MenuButton>
    </div>

    <button class="btn-ghost ml-1 p-2" :title="$t('settings.title')" @click="store.settingsDialog = true"><Settings class="h-4.5 w-4.5" /></button>
  </header>
</template>
