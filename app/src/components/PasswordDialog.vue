<script setup lang="ts">
import { KeyRound } from '@lucide/vue'
import { nextTick, ref, watch } from 'vue'
import { store } from '../store'
import ModalDialog from './ModalDialog.vue'

const password = ref('')
const input = ref<HTMLInputElement>()

watch(
  () => store.passwordRequest,
  async (r) => {
    if (!r) return
    password.value = ''
    await nextTick()
    input.value?.focus()
  },
)

function answer(value: string | null) {
  const r = store.passwordRequest
  store.passwordRequest = null
  r?.resolve(value)
}
</script>

<template>
  <ModalDialog :open="!!store.passwordRequest" :title="$t('password.title')" :subtitle="store.passwordRequest?.path.split('/').pop()" width="max-w-sm" @close="answer(null)">
    <div class="px-5 py-4">
      <label class="block">
        <span class="field-label flex items-center gap-1.5"><KeyRound class="h-3.5 w-3.5" />{{ $t('password.label') }}</span>
        <input ref="input" v-model="password" type="password" class="input" autocomplete="off" @keydown.enter="answer(password)" />
      </label>
      <p v-if="store.passwordRequest?.wrong" class="mt-2 text-xs text-red-600">{{ $t('password.wrong') }}</p>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="answer(null)">{{ $t('common.cancel') }}</button>
      <button class="btn-primary" :disabled="!password" @click="answer(password)">{{ $t('common.open') }}</button>
    </template>
  </ModalDialog>
</template>
