<script setup lang="ts">
import { computed } from 'vue'
import type { ColorValue } from '../api'
import { colorName, cssColor, NAMED_COLORS, SWATCHES } from '../colors'

const props = defineProps<{
  modelValue: ColorValue | undefined
  inherit?: boolean // offer "Default" (no value)
  inherited?: string | null // the default color, for its chip
  allowTex?: boolean // offer "tex" (the \definecolor value), for TeX markers
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string | undefined] }>()

const name = computed(() => colorName(props.modelValue))
const hex = computed(() => cssColor(props.modelValue) ?? props.inherited ?? '#FFEB3B')
const isCustom = computed(() => props.modelValue !== undefined && props.modelValue !== 'tex' && !name.value)
</script>

<template>
  <div class="flex flex-wrap items-center gap-1.5">
    <button
      v-if="inherit"
      :class="['chip flex items-center gap-1.5', modelValue === undefined ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300' : 'border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300']"
      @click="emit('update:modelValue', undefined)"
    >
      <span class="h-3 w-3 rounded-full ring-1 ring-black/10" :style="{ background: inherited ?? '#FFEB3B' }" />{{ $t('form.default') }}
    </button>
    <button
      v-if="allowTex"
      :class="['chip', modelValue === 'tex' ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300' : 'border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-300']"
      :title="$t('form.texColorHint')"
      @click="emit('update:modelValue', 'tex')"
    >
      TeX
    </button>
    <button
      v-for="n in SWATCHES"
      :key="n"
      :title="$t(`colors.${n}`)"
      :class="['h-6 w-6 rounded-full ring-offset-2 transition dark:ring-offset-zinc-900', name === n ? 'ring-2 ring-indigo-500' : 'ring-1 ring-black/10 hover:scale-110']"
      :style="{ background: NAMED_COLORS[n] }"
      @click="emit('update:modelValue', n)"
    />
    <label
      :class="['relative h-6 w-6 cursor-pointer overflow-hidden rounded-full ring-offset-2 dark:ring-offset-zinc-900', isCustom ? 'ring-2 ring-indigo-500' : 'ring-1 ring-black/10']"
      :title="$t('form.customColor')"
      :style="{ background: isCustom ? hex : 'conic-gradient(red, yellow, lime, cyan, blue, magenta, red)' }"
    >
      <input type="color" class="absolute inset-0 cursor-pointer opacity-0" :value="hex" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value.toUpperCase())" />
    </label>
    <span v-if="isCustom" class="mono text-xs text-zinc-500">{{ hex }}</span>
  </div>
</template>
