<script setup lang="ts">
import { Monitor, Moon, Sun } from '@lucide/vue'
import { computed } from 'vue'
import type { Settings } from '../api'
import { saveSettings, store } from '../store'
import ModalDialog from './ModalDialog.vue'

const mod = navigator.platform.toLowerCase().includes('mac') ? '⌘' : 'Ctrl'
const shortcuts = computed(() => [
  [`${mod}+O`, 'settings.kOpen'],
  [`${mod}+S`, 'settings.kSave'],
  [`${mod}+Shift+S`, 'settings.kSaveAs'],
  [`${mod}+${'wheel'}`, 'settings.kZoom'],
  ['Delete', 'settings.kDelete'],
  ['Esc', 'settings.kEsc'],
])
const themes: { value: Settings['theme']; icon: unknown }[] = [
  { value: 'system', icon: Monitor },
  { value: 'light', icon: Sun },
  { value: 'dark', icon: Moon },
]
</script>

<template>
  <ModalDialog :open="store.settingsDialog" :title="$t('settings.title')" width="max-w-md" @close="store.settingsDialog = false">
    <div class="space-y-5 px-5 py-4">
      <label class="block">
        <span class="field-label">{{ $t('settings.language') }}</span>
        <select class="select" :value="store.settings.language ?? ''" @change="saveSettings({ language: (($event.target as HTMLSelectElement).value || null) as Settings['language'] })">
          <option value="">{{ $t('settings.languageSystem') }}</option>
          <option value="en">English</option>
          <option value="zh-CN">简体中文</option>
        </select>
      </label>
      <div>
        <span class="field-label">{{ $t('settings.theme') }}</span>
        <div class="seg">
          <button v-for="th in themes" :key="th.value" :class="store.settings.theme === th.value ? 'seg-active' : 'seg-item'" @click="saveSettings({ theme: th.value })">
            <component :is="th.icon" class="h-3.5 w-3.5" />{{ $t(`settings.theme_${th.value}`) }}
          </button>
        </div>
      </div>
      <div>
        <span class="field-label">{{ $t('settings.shortcuts') }}</span>
        <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
          <template v-for="[key, label] in shortcuts" :key="key">
            <dt><kbd class="mono rounded border border-zinc-300 bg-zinc-50 px-1.5 py-0.5 text-[11px] dark:border-zinc-700 dark:bg-zinc-800">{{ key === `${mod}+wheel` ? `${mod}+${$t('settings.wheel')}` : key }}</kbd></dt>
            <dd class="text-zinc-600 dark:text-zinc-400">{{ $t(label) }}</dd>
          </template>
        </dl>
      </div>
      <p class="border-t border-zinc-200 pt-3 text-xs text-zinc-500 dark:border-zinc-800">
        NotePDF {{ store.meta?.version }} · {{ store.meta?.app_mode ? $t('settings.modeApp') : $t('settings.modeBrowser') }}<template v-if="store.meta?.wsl"> · WSL</template>
        <template v-if="store.meta && !store.meta.fuzzy"><br />{{ $t('settings.noFuzzy') }}</template>
      </p>
    </div>
  </ModalDialog>
</template>
