<script setup lang="ts">
import { FileCode, FolderOpen, RefreshCw, SlidersHorizontal } from '@lucide/vue'
import { computed } from 'vue'
import { pickFile } from '../platform'
import { importTex, openPdf, store } from '../store'
import StyleForm from './StyleForm.vue'
import ToggleSwitch from './ToggleSwitch.vue'

const defaultOutput = computed(() => store.pdf?.path.replace(/\.pdf$/i, '.annotated.pdf') ?? '')
const tex = computed(() => store.config.tex_source)

async function choosePdf() {
  const path = await pickFile('pdf')
  if (path) await openPdf(path)
}

async function chooseOutput() {
  const path = await pickFile('pdf', 'save', store.config.output ?? defaultOutput.value)
  if (path) store.config.output = path
}

function setOutput(v: string) {
  if (v.trim()) store.config.output = v.trim()
  else delete store.config.output
}

function setRemoveExisting(v: boolean) {
  store.config.remove_existing = v
}

function markerLabel(m: { color?: string; macro?: string; env?: string }): string {
  return m.color ? `\\color{${m.color}}` : m.macro ? `\\${m.macro}{…}` : `\\begin{${m.env}}`
}
</script>

<template>
  <div>
    <div class="section space-y-3">
      <span class="panel-title block">{{ $t('doc.files') }}</span>
      <label class="block">
        <span class="field-label">{{ $t('doc.input') }}</span>
        <div class="flex gap-1.5">
          <input class="input-sm mono min-w-0 flex-1" :value="store.pdf?.path ?? ''" readonly :placeholder="$t('top.noPdf')" />
          <button class="btn-secondary btn-sm px-2" :title="$t('doc.change')" @click="choosePdf"><FolderOpen class="h-4 w-4" /></button>
        </div>
      </label>
      <label class="block">
        <span class="field-label">{{ $t('doc.output') }}</span>
        <div class="flex gap-1.5">
          <input class="input-sm mono min-w-0 flex-1" :value="store.config.output ?? ''" :placeholder="defaultOutput" @change="setOutput(($event.target as HTMLInputElement).value)" />
          <button class="btn-secondary btn-sm px-2" :title="$t('doc.change')" @click="chooseOutput"><FolderOpen class="h-4 w-4" /></button>
        </div>
        <span class="hint">{{ $t('doc.outputHint') }}</span>
      </label>
      <div class="flex items-center justify-between gap-3">
        <div>
          <span class="text-[13px] text-zinc-700 dark:text-zinc-300">{{ $t('doc.removeExisting') }}</span>
          <p class="hint mt-0.5">{{ $t('doc.removeExistingHint', { n: store.pdf?.existing ?? 0 }) }}</p>
        </div>
        <ToggleSwitch :model-value="store.config.remove_existing !== false" @update:model-value="setRemoveExisting" />
      </div>
    </div>

    <div class="section">
      <span class="panel-title mb-1 block">{{ $t('doc.defaults') }}</span>
      <p class="hint mb-3">{{ $t('doc.defaultsHint') }}</p>
      <div class="space-y-5">
        <StyleForm :target="store.config.defaults" :inherit="false" part="appearance" />
        <StyleForm :target="store.config.defaults" :inherit="false" part="comment" />
        <StyleForm :target="store.config.defaults" :inherit="false" part="matching" />
      </div>
    </div>

    <div class="section">
      <span class="panel-title mb-3 flex items-center gap-1.5"><SlidersHorizontal class="h-3.5 w-3.5" />{{ $t('editor.advanced') }}</span>
      <StyleForm :target="store.config.defaults" :inherit="false" part="advanced" />
    </div>

    <div class="section">
      <span class="panel-title mb-3 flex items-center gap-1.5"><FileCode class="h-3.5 w-3.5" />{{ $t('doc.tex') }}</span>
      <template v-if="tex">
        <p class="mono truncate text-xs" :title="tex.main">{{ tex.main }}</p>
        <p class="mt-1 text-xs text-zinc-500">
          {{ $t('doc.texMarkers') }}: <span class="mono">{{ tex.markers.map(markerLabel).join(', ') || '—' }}</span>
        </p>
        <div class="mt-3 flex gap-2">
          <button class="btn-secondary btn-sm" @click="importTex(tex)"><RefreshCw class="h-3.5 w-3.5" />{{ $t('doc.reimport') }}</button>
          <button class="btn-ghost btn-sm" @click="store.texDialog = { ...tex }">{{ $t('doc.texSettings') }}</button>
        </div>
      </template>
      <template v-else>
        <p class="hint mt-0">{{ $t('doc.noTex') }}</p>
        <button class="btn-secondary btn-sm mt-2" @click="store.texDialog = { main: '', markers: [{ color: 'revcolor' }] }">{{ $t('top.importTex') }}</button>
      </template>
    </div>
  </div>
</template>
