<script setup lang="ts">
import { Highlighter, RotateCcw, Strikethrough, Underline } from '@lucide/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { AnnotType, Style } from '../api'
import { cssColor } from '../colors'
import { BUILTIN, effective } from '../store'
import BoolField from './BoolField.vue'
import ColorPicker from './ColorPicker.vue'

// Style settings for one entry (inherit = true: unset fields fall back to the document defaults)
// or for the document defaults themselves.
const props = defineProps<{ target: Style; inherit: boolean; part: 'appearance' | 'matching' | 'comment' | 'advanced' }>()
const { t } = useI18n()

const TYPES: { value: AnnotType; icon: unknown }[] = [
  { value: 'highlight', icon: Highlighter },
  { value: 'underline', icon: Underline },
  { value: 'strikeout', icon: Strikethrough },
  { value: 'squiggly', icon: null },
]

/** What an unset field resolves to: the document default for entries, the built-in value for defaults. */
function base<K extends keyof Style>(key: K): Required<Style>[K] {
  return props.inherit ? effective(null, key) : BUILTIN[key]
}
function value<K extends keyof Style>(key: K): Required<Style>[K] {
  const own = props.target[key]
  return own === undefined || own === null || own === '' ? base(key) : (own as Required<Style>[K])
}
function set<K extends keyof Style>(key: K, v: Style[K] | undefined) {
  if (v === undefined || v === null || v === '' || (!props.inherit && v === BUILTIN[key])) delete props.target[key]
  else props.target[key] = v
}

const opacity = computed({
  get: () => Number(value('opacity')),
  set: (v: number) => set('opacity', Math.round(v * 100) / 100),
})

// Occurrence: first | all | one number | several numbers.
const occMode = computed(() => {
  const own = props.target.occurrence
  if (own === undefined) return props.inherit ? '' : 'first'
  return typeof own === 'string' ? own : 'nth'
})
const occText = computed(() => {
  const own = props.target.occurrence
  return Array.isArray(own) ? own.join(', ') : typeof own === 'number' ? String(own) : ''
})
function setOccMode(mode: string) {
  if (mode === '') set('occurrence', undefined)
  else if (mode === 'nth') set('occurrence', typeof props.target.occurrence === 'number' || Array.isArray(props.target.occurrence) ? props.target.occurrence : 1)
  else set('occurrence', mode as 'first' | 'all')
}
function setOccText(text: string) {
  const nums = text.split(/[\s,]+/).filter(Boolean).map(Number)
  if (!nums.length || nums.some((n) => !Number.isInteger(n) || n < 1)) return
  set('occurrence', nums.length === 1 ? nums[0] : nums)
}

const contMode = computed(() => {
  const own = props.target.continuation_comment
  if (own === undefined) return props.inherit ? '' : 'none'
  return own === 'none' || own === 'same' ? own : 'custom'
})
function setContMode(mode: string) {
  if (mode === '') set('continuation_comment', undefined)
  else if (mode === 'custom') props.target.continuation_comment = t('form.continuedText')
  else set('continuation_comment', mode)
}

function defaultLabel<K extends keyof Style>(key: K, label: (v: Required<Style>[K]) => string): string {
  return `${t('form.default')} · ${label(base(key))}`
}
const occLabel = (v: Style['occurrence']) => (v === 'first' || v === 'all' ? t(`form.occ_${v}`) : String(v))
</script>

<template>
  <div class="space-y-4">
    <template v-if="part === 'appearance'">
      <div>
        <span class="field-label">{{ $t('form.type') }}</span>
        <div class="seg">
          <button
            v-for="ty in TYPES"
            :key="ty.value"
            :class="[
              'flex-col gap-0.5 py-1.5 text-[11px]',
              value('type') === ty.value ? (target.type === undefined && inherit ? 'seg-item bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300' : 'seg-active') : 'seg-item',
            ]"
            :title="inherit && target.type === undefined && value('type') === ty.value ? $t('form.default') : $t(`types.${ty.value}`)"
            @click="set('type', target.type === ty.value && inherit ? undefined : ty.value)"
          >
            <component :is="ty.icon" v-if="ty.icon" class="h-3.5 w-3.5" />
            <span v-else class="h-3.5 text-[13px] leading-none">〰</span>
            {{ $t(`types.${ty.value}`) }}
          </button>
        </div>
      </div>
      <div>
        <span class="field-label">{{ $t('form.color') }}</span>
        <ColorPicker
          :model-value="target.color"
          :inherit="inherit"
          :inherited="cssColor(base('color'))"
          @update:model-value="(v) => set('color', v ?? (inherit ? undefined : 'yellow'))"
        />
      </div>
      <div>
        <div class="flex items-center justify-between">
          <span class="field-label">{{ $t('form.opacity') }}</span>
          <span class="flex items-center gap-1.5 text-xs text-zinc-500 tabular-nums">
            {{ Math.round(opacity * 100) }}%
            <button v-if="inherit && target.opacity !== undefined" class="text-zinc-400 hover:text-zinc-700" :title="$t('form.reset')" @click="set('opacity', undefined)">
              <RotateCcw class="h-3 w-3" />
            </button>
          </span>
        </div>
        <input v-model.number="opacity" type="range" min="0.1" max="1" step="0.05" class="w-full accent-indigo-600" />
      </div>
    </template>

    <template v-else-if="part === 'matching'">
      <div class="space-y-3">
        <label class="block">
          <span class="field-label">{{ $t('form.match') }}</span>
          <select class="select" :value="target.match ?? (inherit ? '' : 'normalized')" @change="set('match', (($event.target as HTMLSelectElement).value || undefined) as Style['match'])">
            <option v-if="inherit" value="">{{ defaultLabel('match', (v) => $t(`form.match_${v}`)) }}</option>
            <option value="normalized">{{ $t('form.match_normalized') }}</option>
            <option value="exact">{{ $t('form.match_exact') }}</option>
            <option value="fuzzy">{{ $t('form.match_fuzzy') }}</option>
          </select>
        </label>
        <label class="block">
          <span class="field-label">{{ $t('form.occurrence') }}</span>
          <select class="select" :value="occMode" @change="setOccMode(($event.target as HTMLSelectElement).value)">
            <option v-if="inherit" value="">{{ defaultLabel('occurrence', occLabel) }}</option>
            <option value="first">{{ $t('form.occ_first') }}</option>
            <option value="all">{{ $t('form.occ_all') }}</option>
            <option value="nth">{{ $t('form.occ_nth') }}</option>
          </select>
        </label>
      </div>
      <label v-if="occMode === 'nth'" class="block">
        <input class="input-sm" :value="occText" :placeholder="$t('form.occNthPlaceholder')" @change="setOccText(($event.target as HTMLInputElement).value)" />
        <span class="hint">{{ $t('form.occNthHint') }}</span>
      </label>
      <p class="hint -mt-2">{{ $t(`form.matchHint_${value('match')}`) }}</p>
      <BoolField :label="$t('form.caseSensitive')" :model-value="target.case_sensitive" :inherit="inherit" :inherited="base('case_sensitive')" @update:model-value="(v) => set('case_sensitive', v)" />
      <BoolField :label="$t('form.wholeWord')" :model-value="target.whole_word" :inherit="inherit" :inherited="base('whole_word')" @update:model-value="(v) => set('whole_word', v)" />
    </template>

    <template v-else-if="part === 'comment'">
      <div class="space-y-3">
        <label class="block">
          <span class="field-label">{{ $t('form.popup') }}</span>
          <select class="select" :value="target.popup ?? (inherit ? '' : 'closed')" @change="set('popup', (($event.target as HTMLSelectElement).value || undefined) as Style['popup'])">
            <option v-if="inherit" value="">{{ defaultLabel('popup', (v) => $t(`form.popup_${v}`)) }}</option>
            <option value="closed">{{ $t('form.popup_closed') }}</option>
            <option value="open">{{ $t('form.popup_open') }}</option>
            <option value="none">{{ $t('form.popup_none') }}</option>
          </select>
        </label>
        <label class="block">
          <span class="field-label">{{ $t('form.author') }}</span>
          <input class="input-sm" :value="target.author ?? ''" :placeholder="base('author') || '—'" @input="set('author', ($event.target as HTMLInputElement).value)" />
        </label>
      </div>
      <label v-if="!inherit" class="block">
        <span class="field-label">{{ $t('form.subject') }}</span>
        <input class="input-sm" :value="target.subject ?? ''" :placeholder="BUILTIN.subject" @input="set('subject', ($event.target as HTMLInputElement).value)" />
      </label>
      <BoolField
        :label="$t('form.stickyNote')"
        :hint="$t('form.stickyNoteHint')"
        :model-value="target.sticky_note"
        :inherit="inherit"
        :inherited="base('sticky_note')"
        @update:model-value="(v) => set('sticky_note', v)"
      />
    </template>

    <template v-else>
      <BoolField :label="$t('form.sequential')" :hint="$t('form.sequentialHint')" :model-value="target.sequential" :inherit="inherit" :inherited="base('sequential')" @update:model-value="(v) => set('sequential', v)" />
      <BoolField :label="$t('form.fuzzyFallback')" :hint="$t('form.fuzzyFallbackHint')" :model-value="target.fuzzy_fallback" :inherit="inherit" :inherited="base('fuzzy_fallback')" @update:model-value="(v) => set('fuzzy_fallback', v)" />
      <BoolField :label="$t('form.splitFallback')" :hint="$t('form.splitFallbackHint')" :model-value="target.split_fallback" :inherit="inherit" :inherited="base('split_fallback')" @update:model-value="(v) => set('split_fallback', v)" />
      <div class="space-y-3">
        <label class="block">
          <span class="field-label">{{ $t('form.continuation') }}</span>
          <select class="select" :value="contMode" @change="setContMode(($event.target as HTMLSelectElement).value)">
            <option v-if="inherit" value="">{{ $t('form.default') }}</option>
            <option value="none">{{ $t('form.cont_none') }}</option>
            <option value="same">{{ $t('form.cont_same') }}</option>
            <option value="custom">{{ $t('form.cont_custom') }}</option>
          </select>
        </label>
        <label class="block">
          <span class="field-label">{{ $t('form.fuzzyThreshold') }}</span>
          <input
            class="input-sm"
            type="number"
            min="50"
            max="100"
            :value="target.fuzzy_threshold ?? ''"
            :placeholder="String(base('fuzzy_threshold'))"
            @change="set('fuzzy_threshold', ($event.target as HTMLInputElement).value === '' ? undefined : Number(($event.target as HTMLInputElement).value))"
          />
        </label>
      </div>
      <input
        v-if="contMode === 'custom'"
        class="input-sm"
        :value="target.continuation_comment"
        @input="set('continuation_comment', ($event.target as HTMLInputElement).value || undefined)"
      />
      <p class="hint -mt-2">{{ $t('form.continuationHint') }}</p>
    </template>
  </div>
</template>
