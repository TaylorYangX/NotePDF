<script setup lang="ts">
import { Highlighter, MessageSquarePlus, Strikethrough, Underline, X } from '@lucide/vue'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { AnnotType, Entry } from '../api'
import { cssColor, NAMED_COLORS, SWATCHES } from '../colors'
import { addFromSelection, effective } from '../store'

const props = defineProps<{ x: number; y: number; page: number; range: [number, number] }>()
const emit = defineEmits<{ done: [] }>()

const defaultHex = cssColor(effective(null, 'color'))
const color = ref<string>(SWATCHES.find((n) => NAMED_COLORS[n] === defaultHex) ?? SWATCHES[0])
const commenting = ref(false)
const comment = ref('')
const busy = ref(false)
const textarea = ref<HTMLTextAreaElement>()

async function add(type: AnnotType = 'highlight', withComment = false) {
  if (busy.value) return
  const fields: Omit<Partial<Entry>, '_id'> = {}
  if (NAMED_COLORS[color.value] !== defaultHex) fields.color = color.value
  if (type !== effective(null, 'type')) fields.type = type
  if (withComment && comment.value.trim()) fields.comment = comment.value.trim()
  busy.value = true
  await addFromSelection(props.page, props.range[0], props.range[1], fields)
  busy.value = false
  emit('done')
}

async function startComment() {
  commenting.value = true
  await nextTick()
  textarea.value?.focus()
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('done')
}

function onCommentKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    add('highlight', true)
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    class="card absolute z-20 w-[320px] cursor-default p-2 shadow-xl"
    :style="{ left: `${x}px`, top: `${y}px` }"
    @mousedown.stop
    @mousemove.stop
    @dblclick.stop
  >
    <div class="flex items-center gap-1">
      <button
        v-for="name in SWATCHES.slice(0, 6)"
        :key="name"
        :title="$t(`colors.${name}`)"
        :class="['h-5 w-5 rounded-full ring-offset-1 transition dark:ring-offset-zinc-900', color === name ? 'ring-2 ring-indigo-500' : 'hover:scale-110']"
        :style="{ background: NAMED_COLORS[name] }"
        @click="color = name"
      />
      <div class="flex-1" />
      <button class="btn-ghost p-1" :title="$t('common.close')" @click="emit('done')"><X class="h-3.5 w-3.5" /></button>
    </div>

    <div v-if="!commenting" class="mt-2 grid grid-cols-[1fr_auto_auto_auto] gap-1">
      <button class="btn-primary btn-sm" :disabled="busy" @click="add('highlight')"><Highlighter class="h-3.5 w-3.5" />{{ $t('selection.highlight') }}</button>
      <button class="btn-secondary btn-sm" :disabled="busy" :title="$t('types.underline')" @click="add('underline')"><Underline class="h-3.5 w-3.5" /></button>
      <button class="btn-secondary btn-sm" :disabled="busy" :title="$t('types.strikeout')" @click="add('strikeout')"><Strikethrough class="h-3.5 w-3.5" /></button>
      <button class="btn-secondary btn-sm" :disabled="busy" @click="startComment"><MessageSquarePlus class="h-3.5 w-3.5" />{{ $t('selection.comment') }}</button>
    </div>
    <div v-else class="mt-2">
      <textarea
        ref="textarea"
        v-model="comment"
        rows="3"
        class="input-sm resize-none"
        :placeholder="$t('selection.commentPlaceholder')"
        @keydown="onCommentKey"
      />
      <div class="mt-1.5 flex items-center justify-between gap-2">
        <span class="text-[11px] text-zinc-400">{{ $t('selection.enterHint') }}</span>
        <button class="btn-primary btn-sm" :disabled="busy" @click="add('highlight', true)">{{ $t('selection.add') }}</button>
      </div>
    </div>
  </div>
</template>
