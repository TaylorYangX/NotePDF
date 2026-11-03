<script setup lang="ts">
import ToggleSwitch from './ToggleSwitch.vue'

// A yes/no setting. On an entry it can also be left to the document default.
const props = defineProps<{ label: string; hint?: string; modelValue: boolean | undefined; inherit: boolean; inherited: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean | undefined] }>()

function set(v: boolean | undefined) {
  emit('update:modelValue', v)
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between gap-3">
      <span class="text-[13px] text-zinc-700 dark:text-zinc-300">{{ label }}</span>
      <div v-if="inherit" class="seg w-44 shrink-0">
        <button :class="props.modelValue === undefined ? 'seg-active' : 'seg-item'" @click="set(undefined)">
          {{ $t('form.default') }} · {{ inherited ? $t('form.on') : $t('form.off') }}
        </button>
        <button :class="props.modelValue === true ? 'seg-active' : 'seg-item'" @click="set(true)">{{ $t('form.on') }}</button>
        <button :class="props.modelValue === false ? 'seg-active' : 'seg-item'" @click="set(false)">{{ $t('form.off') }}</button>
      </div>
      <ToggleSwitch v-else :model-value="props.modelValue ?? inherited" :label="label" @update:model-value="set" />
    </div>
    <p v-if="hint" class="hint mt-1">{{ hint }}</p>
  </div>
</template>
