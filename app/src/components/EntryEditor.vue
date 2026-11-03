<script setup lang="ts">
import { ChevronRight, CircleAlert, CircleCheck, Copy, Crosshair, Regex, Trash, TriangleAlert, Type } from '@lucide/vue'
import { computed, ref } from 'vue'
import type { Entry, PagesValue } from '../api'
import { translateMessage } from '../i18n'
import { duplicateEntry, focusEntry, removeEntry, store } from '../store'
import BoolField from './BoolField.vue'
import ColorPicker from './ColorPicker.vue'
import StyleForm from './StyleForm.vue'

const props = defineProps<{ entry: Entry }>()
// Placeholders shown in the hint; kept out of the template, where "}}" would end the interpolation.
const GAPS = { gap: '{' + '{gap}}', gapN: '{' + '{gap:40}}' }
const advanced = ref(false)

const preview = computed(() => store.preview[props.entry._id])
const isRegex = computed(() => props.entry.regex !== undefined)
const pages = computed(() => [...new Set((preview.value?.hits ?? []).map((h) => h.page + 1))])

function setField<K extends keyof Entry>(key: K, v: Entry[K] | undefined) {
  if (v === undefined || v === null || v === '') delete props.entry[key]
  else props.entry[key] = v
}

function toggleRegex(on: boolean) {
  if (on === isRegex.value) return
  if (on) {
    props.entry.regex = props.entry.text ?? ''
    delete props.entry.text
  } else {
    props.entry.text = props.entry.regex ?? ''
    delete props.entry.regex
  }
}

const pagesText = computed(() => {
  const p = props.entry.pages
  return p === undefined ? '' : Array.isArray(p) ? p.join(', ') : String(p)
})
function setPages(text: string) {
  const s = text.trim()
  const value: PagesValue | undefined = !s ? undefined : /^\d+$/.test(s) ? Number(s) : s
  setField('pages', value)
}
</script>

<template>
  <div>
    <!-- what to find -->
    <div class="section space-y-3">
      <div class="flex items-center justify-between">
        <span class="panel-title">{{ $t('editor.find') }}</span>
        <div class="seg w-40">
          <button :class="!isRegex ? 'seg-active' : 'seg-item'" @click="toggleRegex(false)"><Type class="h-3.5 w-3.5" />{{ $t('editor.text') }}</button>
          <button :class="isRegex ? 'seg-active' : 'seg-item'" @click="toggleRegex(true)"><Regex class="h-3.5 w-3.5" />{{ $t('editor.regex') }}</button>
        </div>
      </div>
      <textarea
        v-if="!isRegex"
        class="input resize-y text-[13px] leading-relaxed"
        rows="4"
        :value="entry.text"
        :placeholder="$t('editor.textPlaceholder')"
        @input="entry.text = ($event.target as HTMLTextAreaElement).value"
      />
      <textarea
        v-else
        class="input mono resize-y"
        rows="2"
        :value="entry.regex"
        :placeholder="$t('editor.regexPlaceholder')"
        @input="entry.regex = ($event.target as HTMLTextAreaElement).value"
      />
      <p class="hint -mt-1">{{ isRegex ? $t('editor.regexHint') : $t('editor.gapHint', GAPS) }}</p>

      <div
        v-if="preview"
        :class="[
          'rounded-lg border px-3 py-2 text-xs',
          preview.status === 'found' && 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200',
          preview.status === 'warning' && 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200',
          (preview.status === 'missing' || preview.status === 'invalid') && 'border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200',
        ]"
      >
        <div class="flex items-start gap-2">
          <CircleCheck v-if="preview.status === 'found'" class="mt-px h-3.5 w-3.5 shrink-0" />
          <TriangleAlert v-else-if="preview.status === 'warning'" class="mt-px h-3.5 w-3.5 shrink-0" />
          <CircleAlert v-else class="mt-px h-3.5 w-3.5 shrink-0" />
          <div class="min-w-0 flex-1 space-y-0.5">
            <p v-if="preview.status === 'invalid'">{{ preview.error }}</p>
            <p v-else-if="!preview.hits.length">{{ $t('editor.notFound') }}</p>
            <p v-else>{{ $t('editor.foundOn', { n: preview.hits.length, pages: pages.join(', ') }) }}</p>
            <p v-for="(w, k) in preview.warnings" :key="k">{{ translateMessage(w) }}</p>
          </div>
          <button v-if="preview.hits.length" class="shrink-0 opacity-70 hover:opacity-100" :title="$t('editor.showInPdf')" @click="focusEntry(entry._id)">
            <Crosshair class="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      <StyleForm :target="entry" :inherit="true" part="matching" />
    </div>

    <!-- appearance -->
    <div class="section">
      <span class="panel-title mb-3 block">{{ $t('editor.appearance') }}</span>
      <StyleForm :target="entry" :inherit="true" part="appearance" />
    </div>

    <!-- comment -->
    <div class="section space-y-3">
      <span class="panel-title block">{{ $t('editor.comment') }}</span>
      <textarea
        class="input resize-y text-[13px]"
        rows="3"
        :value="entry.comment ?? ''"
        :placeholder="$t('editor.commentPlaceholder')"
        @input="setField('comment', ($event.target as HTMLTextAreaElement).value)"
      />
      <StyleForm :target="entry" :inherit="true" part="comment" />
    </div>

    <!-- where -->
    <div class="section space-y-3">
      <span class="panel-title block">{{ $t('editor.where') }}</span>
      <label class="block">
        <span class="field-label">{{ $t('editor.pages') }}</span>
        <input class="input-sm" :value="pagesText" :placeholder="$t('editor.pagesPlaceholder')" @change="setPages(($event.target as HTMLInputElement).value)" />
        <span class="hint">{{ $t('editor.pagesHint') }}</span>
      </label>
      <div class="grid grid-cols-2 gap-3">
        <label>
          <span class="field-label">{{ $t('editor.contextBefore') }}</span>
          <input class="input-sm" :value="entry.context_before ?? ''" @input="setField('context_before', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span class="field-label">{{ $t('editor.contextAfter') }}</span>
          <input class="input-sm" :value="entry.context_after ?? ''" @input="setField('context_after', ($event.target as HTMLInputElement).value)" />
        </label>
      </div>
      <p class="hint -mt-1">{{ $t('editor.contextHint') }}</p>
    </div>

    <!-- advanced -->
    <div class="section">
      <button class="flex w-full items-center gap-1 panel-title" @click="advanced = !advanced">
        <ChevronRight :class="['h-3.5 w-3.5 transition', advanced && 'rotate-90']" />{{ $t('editor.advanced') }}
      </button>
      <div v-if="advanced" class="mt-3 space-y-4">
        <StyleForm :target="entry" :inherit="true" part="advanced" />
        <BoolField
          :label="$t('editor.required')"
          :hint="$t('editor.requiredHint')"
          :model-value="entry.required"
          :inherit="false"
          :inherited="true"
          @update:model-value="(v) => setField('required', v === true ? undefined : v)"
        />
        <div>
          <span class="field-label">{{ $t('editor.textColor') }}</span>
          <ColorPicker :model-value="entry.text_color" :inherit="true" :inherited="null" @update:model-value="(v) => setField('text_color', v)" />
          <p class="hint">{{ $t('editor.textColorHint') }}</p>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <label>
            <span class="field-label">{{ $t('editor.group') }}</span>
            <input class="input-sm" :value="entry.group ?? ''" @input="setField('group', ($event.target as HTMLInputElement).value)" />
          </label>
          <label>
            <span class="field-label">{{ $t('editor.source') }}</span>
            <input class="input-sm mono" :value="entry.source ?? ''" @input="setField('source', ($event.target as HTMLInputElement).value)" />
          </label>
        </div>
        <p class="hint -mt-2">{{ $t('editor.groupHint') }}</p>
      </div>
    </div>

    <div class="flex gap-2 px-4 py-4">
      <button class="btn-secondary btn-sm flex-1" @click="duplicateEntry(entry._id)"><Copy class="h-3.5 w-3.5" />{{ $t('list.duplicate') }}</button>
      <button class="btn-danger btn-sm flex-1" @click="removeEntry(entry._id)"><Trash class="h-3.5 w-3.5" />{{ $t('list.delete') }}</button>
    </div>
    <p class="px-4 pb-4 text-[11px] text-zinc-400">{{ $t('editor.keyHint') }}</p>
  </div>
</template>
