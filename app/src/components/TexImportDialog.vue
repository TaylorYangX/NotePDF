<script setup lang="ts">
import { FolderOpen, LoaderCircle, Plus, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { MarkerSpec, TexSource } from '../api'
import { pickFile } from '../platform'
import { importTex, store } from '../store'
import ColorPicker from './ColorPicker.vue'
import ModalDialog from './ModalDialog.vue'
import ToggleSwitch from './ToggleSwitch.vue'

type Kind = 'color' | 'macro' | 'env'
interface MarkerRow {
  kind: Kind
  name: string
  highlight?: string
  comment?: string
}

const main = ref('')
const markers = ref<MarkerRow[]>([])
const detectMacros = ref(true)
const captions = ref(true)
const footnotes = ref(true)
const replacements = ref<{ from: string; to: string }[]>([])
const busy = ref(false)

const open = computed(() => store.texDialog !== null)

watch(
  () => store.texDialog,
  (d) => {
    if (!d) return
    main.value = d.main
    markers.value = (d.markers.length ? d.markers : [{ color: 'revcolor' }]).map(toRow)
    detectMacros.value = d.detect_macros ?? true
    captions.value = d.include_captions ?? true
    footnotes.value = d.include_footnotes ?? true
    replacements.value = Object.entries(d.replacements ?? {}).map(([from, to]) => ({ from, to }))
  },
)

function toRow(m: MarkerSpec): MarkerRow {
  const kind: Kind = m.macro !== undefined ? 'macro' : m.env !== undefined ? 'env' : 'color'
  return { kind, name: (m[kind] ?? '') as string, highlight: m.highlight, comment: m.comment }
}

function toSpec(r: MarkerRow): MarkerSpec {
  const spec: MarkerSpec = { [r.kind]: r.name.trim().replace(/^\\/, '') }
  if (r.highlight) spec.highlight = r.highlight
  if (r.comment?.trim()) spec.comment = r.comment.trim()
  return spec
}

function example(m: MarkerRow): string {
  const n = m.name.trim().replace(/^\\/, '') || '…'
  if (m.kind === 'macro') return `\\${n}{…}   \\${n}[…]{…}`
  if (m.kind === 'env') return `\\begin{${n}} … \\end{${n}}`
  return `{\\color{${n}} …}   \\textcolor{${n}}{…}`
}

async function browse() {
  const path = await pickFile('tex', 'open', main.value || undefined)
  if (path) main.value = path
}

const valid = computed(() => main.value.trim() && markers.value.some((m) => m.name.trim()))

async function run() {
  if (!valid.value) return
  const tex: TexSource = {
    main: main.value.trim(),
    markers: markers.value.filter((m) => m.name.trim()).map(toSpec),
  }
  if (!detectMacros.value) tex.detect_macros = false
  if (!captions.value) tex.include_captions = false
  if (!footnotes.value) tex.include_footnotes = false
  const repl = Object.fromEntries(replacements.value.filter((r) => r.from.trim()).map((r) => [r.from.trim(), r.to]))
  if (Object.keys(repl).length) tex.replacements = repl
  busy.value = true
  const ok = await importTex(tex)
  busy.value = false
  if (ok) store.texDialog = null
}
</script>

<template>
  <ModalDialog :open="open" :title="$t('tex.title')" :subtitle="$t('tex.subtitle')" width="max-w-2xl" @close="store.texDialog = null">
    <div class="space-y-5 px-5 py-4">
      <label class="block">
        <span class="field-label">{{ $t('tex.main') }}</span>
        <div class="flex gap-1.5">
          <input v-model="main" class="input-sm mono flex-1" :placeholder="$t('tex.mainPlaceholder')" />
          <button class="btn-secondary btn-sm" @click="browse"><FolderOpen class="h-4 w-4" />{{ $t('tex.browse') }}</button>
        </div>
        <span class="hint">{{ $t('tex.mainHint') }}</span>
      </label>

      <div>
        <span class="field-label">{{ $t('tex.markers') }}</span>
        <div class="space-y-2">
          <div v-for="(m, k) in markers" :key="k" class="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
            <div class="flex items-center gap-2">
              <select v-model="m.kind" class="select w-36 shrink-0 text-[13px]">
                <option value="color">{{ $t('tex.kind_color') }}</option>
                <option value="macro">{{ $t('tex.kind_macro') }}</option>
                <option value="env">{{ $t('tex.kind_env') }}</option>
              </select>
              <input v-model="m.name" class="input-sm mono flex-1" :placeholder="$t(`tex.name_${m.kind}`)" />
              <button class="btn-ghost p-1.5" :disabled="markers.length === 1" :title="$t('list.delete')" @click="markers.splice(k, 1)"><X class="h-4 w-4" /></button>
            </div>
            <p class="mono mt-1.5 text-[11px] text-zinc-400">{{ example(m) }}</p>
            <div class="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-2">
              <span class="text-xs text-zinc-500">{{ $t('tex.highlight') }}</span>
              <ColorPicker v-model="m.highlight" :inherit="true" :inherited="null" :allow-tex="m.kind === 'color'" />
            </div>
            <input v-model="m.comment" class="input-sm mt-2.5" :placeholder="$t('tex.fallbackComment', { example: 'Revised ({file}:{line})' })" />
          </div>
          <button class="btn-ghost btn-sm" @click="markers.push({ kind: 'color', name: '' })"><Plus class="h-3.5 w-3.5" />{{ $t('tex.addMarker') }}</button>
        </div>
      </div>

      <div class="rounded-lg bg-indigo-50 px-3.5 py-2.5 text-xs leading-relaxed text-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-200">
        {{ $t('tex.noteHelp', { note: '%@note:' }) }}
        <code class="mono mt-1 block text-[11.5px] opacity-80">{{ '{\\color{revcolor} %@note: R1.2 clarified the motivation' }}<br />{{ 'We now ...}' }}</code>
      </div>

      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <span class="text-[13px]">{{ $t('tex.detectMacros') }}</span>
            <p class="hint mt-0.5">{{ $t('tex.detectMacrosHint') }}</p>
          </div>
          <ToggleSwitch v-model="detectMacros" />
        </div>
        <div class="flex items-center justify-between gap-3">
          <span class="text-[13px]">{{ $t('tex.captions') }}</span>
          <ToggleSwitch v-model="captions" />
        </div>
        <div class="flex items-center justify-between gap-3">
          <span class="text-[13px]">{{ $t('tex.footnotes') }}</span>
          <ToggleSwitch v-model="footnotes" />
        </div>
      </div>

      <div>
        <span class="field-label">{{ $t('tex.replacements') }}</span>
        <p class="hint mt-0 mb-2">{{ $t('tex.replacementsHint') }}</p>
        <div v-for="(r, k) in replacements" :key="k" class="mb-1.5 flex items-center gap-1.5">
          <input v-model="r.from" class="input-sm mono w-40" placeholder="\etal" />
          <span class="text-zinc-400">→</span>
          <input v-model="r.to" class="input-sm flex-1" placeholder="et al." />
          <button class="btn-ghost p-1.5" @click="replacements.splice(k, 1)"><X class="h-4 w-4" /></button>
        </div>
        <button class="btn-ghost btn-sm" @click="replacements.push({ from: '', to: '' })"><Plus class="h-3.5 w-3.5" />{{ $t('tex.addReplacement') }}</button>
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="store.texDialog = null">{{ $t('common.cancel') }}</button>
      <button class="btn-primary" :disabled="!valid || busy" @click="run">
        <LoaderCircle v-if="busy" class="h-4 w-4 animate-spin" />{{ $t('tex.import') }}
      </button>
    </template>
  </ModalDialog>
</template>
