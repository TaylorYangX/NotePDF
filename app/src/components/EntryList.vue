<script setup lang="ts">
import { ArrowDown, ArrowUp, Copy, MessageSquareText, MousePointerClick, Plus, Trash } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'
import type { Entry } from '../api'
import { cssColor } from '../colors'
import { translateMessage } from '../i18n'
import { addEntry, displayText, duplicateEntry, effective, entryStatus, moveEntry, removeEntry, selectEntry, store } from '../store'
import StatusIcon from './StatusIcon.vue'

const list = ref<HTMLElement>()

const rows = computed(() => {
  const all = store.config.annotations.map((entry, index) => ({ entry, index, status: entryStatus(entry._id) }))
  if (store.filter === 'missing') return all.filter((r) => r.status === 'missing' || r.status === 'invalid')
  if (store.filter === 'warning') return all.filter((r) => r.status === 'warning')
  return all
})

const noteCount = computed(() => store.notes.length)

function groupLabel(e: Entry): string {
  const n = e.group?.replace(/^rev-/, '')
  const file = e.source?.split(':')[0]
  return [n ? `#${n}` : '', file].filter(Boolean).join(' · ')
}

function pagesLabel(e: Entry): string | null {
  if (e.pages === undefined || e.pages === '' || (Array.isArray(e.pages) && !e.pages.length)) return null
  return Array.isArray(e.pages) ? e.pages.join(', ') : String(e.pages)
}

function hitPages(id: string): string | null {
  const hits = store.preview[id]?.hits ?? []
  const pages = [...new Set(hits.map((h) => h.page + 1))]
  if (!pages.length) return null
  return pages.length > 3 ? `${pages.slice(0, 3).join(', ')}…` : pages.join(', ')
}

watch(
  () => store.selected,
  async (id) => {
    await nextTick()
    list.value?.querySelector(`[data-entry="${id}"]`)?.scrollIntoView({ block: 'nearest' })
  },
)

function noteSource(m: { params: Record<string, unknown> }): string | null {
  return (m.params.source as string | undefined)?.split('/').pop() ?? null
}
</script>

<template>
  <div class="flex border-b border-zinc-200 px-2 dark:border-zinc-800">
    <button :class="store.leftTab === 'entries' ? 'tab-active' : 'tab'" @click="store.leftTab = 'entries'">
      {{ $t('list.entries') }} <span class="ml-1 text-xs text-zinc-400">{{ store.config.annotations.length }}</span>
    </button>
    <button :class="store.leftTab === 'notes' ? 'tab-active' : 'tab'" @click="store.leftTab = 'notes'">
      {{ $t('list.notes') }}
      <span v-if="noteCount" class="ml-1 rounded-full bg-amber-100 px-1.5 text-[11px] text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">{{ noteCount }}</span>
    </button>
  </div>

  <template v-if="store.leftTab === 'entries'">
    <div class="flex items-center gap-2 px-3 py-2">
      <div class="seg flex-1">
        <button :class="store.filter === 'all' ? 'seg-active' : 'seg-item'" @click="store.filter = 'all'">{{ $t('list.all') }}</button>
        <button :class="store.filter === 'missing' ? 'seg-active' : 'seg-item'" @click="store.filter = 'missing'">{{ $t('list.missing') }}</button>
        <button :class="store.filter === 'warning' ? 'seg-active' : 'seg-item'" @click="store.filter = 'warning'">{{ $t('list.warnings') }}</button>
      </div>
      <button class="btn-secondary btn-sm px-2" :title="$t('list.add')" @click="addEntry({ text: '' })"><Plus class="h-4 w-4" /></button>
    </div>

    <div ref="list" class="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
      <div v-if="!store.config.annotations.length" class="mx-2 mt-6 rounded-xl border border-dashed border-zinc-300 p-5 text-center text-sm text-zinc-500 dark:border-zinc-700">
        <MousePointerClick class="mx-auto mb-2 h-6 w-6 text-zinc-400" />
        <p>{{ $t('list.emptyTitle') }}</p>
        <p class="mt-1 text-xs">{{ $t('list.emptyHint') }}</p>
      </div>
      <div v-else-if="!rows.length" class="mt-6 text-center text-sm text-zinc-500">{{ $t('list.noneMatch') }}</div>

      <template v-for="(row, k) in rows" :key="row.entry._id">
        <div
          v-if="row.entry.group && row.entry.group !== rows[k - 1]?.entry.group"
          class="mt-3 mb-1 flex items-center gap-2 px-2 text-[11px] font-medium text-zinc-400"
        >
          <span class="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />{{ groupLabel(row.entry) }}<span class="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
        </div>
        <div
          :data-entry="row.entry._id"
          :class="[
            'group relative mb-1 cursor-pointer rounded-lg border px-2.5 py-2 transition',
            store.selected === row.entry._id
              ? 'border-indigo-300 bg-indigo-50 dark:border-indigo-700 dark:bg-indigo-950/50'
              : 'border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-800/60',
          ]"
          @click="selectEntry(row.entry._id)"
        >
          <div class="flex items-start gap-2">
            <StatusIcon :status="row.status" class="mt-0.5" />
            <span
              class="mt-0.5 h-3.5 w-3.5 shrink-0 rounded-sm ring-1 ring-black/10"
              :style="{ background: cssColor(effective(row.entry, 'color')) ?? '#FFEB3B', opacity: 0.4 + Number(effective(row.entry, 'opacity')) * 0.6 }"
            />
            <div class="min-w-0 flex-1">
              <p :class="['line-clamp-2 text-[13px] leading-snug break-words', row.entry.regex !== undefined && 'mono', !displayText(row.entry) && 'text-zinc-400 italic']">
                {{ displayText(row.entry) || $t('list.untitled') }}
              </p>
              <p v-if="row.entry.comment" class="mt-0.5 flex items-center gap-1 truncate text-xs text-zinc-500 dark:text-zinc-400">
                <MessageSquareText class="h-3 w-3 shrink-0" /><span class="truncate">{{ row.entry.comment }}</span>
              </p>
              <p
                v-if="store.preview[row.entry._id]?.status === 'invalid'"
                class="mt-0.5 line-clamp-2 text-xs text-red-600 dark:text-red-400"
              >
                {{ store.preview[row.entry._id]?.error }}
              </p>
              <p v-else-if="store.preview[row.entry._id]?.warnings.length" class="mt-0.5 truncate text-xs text-amber-600 dark:text-amber-400">
                {{ translateMessage(store.preview[row.entry._id]!.warnings[0]) }}
              </p>
              <div class="mt-1 flex flex-wrap gap-1 text-[10.5px] text-zinc-500">
                <span v-if="hitPages(row.entry._id)" class="rounded bg-zinc-100 px-1.5 py-px dark:bg-zinc-800">{{ $t('list.onPages', { pages: hitPages(row.entry._id) }) }}</span>
                <span v-if="pagesLabel(row.entry)" class="rounded bg-sky-50 px-1.5 py-px text-sky-700 dark:bg-sky-950 dark:text-sky-300">{{ $t('list.pagesOnly', { pages: pagesLabel(row.entry) }) }}</span>
                <span v-if="row.entry.source" class="mono rounded bg-violet-50 px-1.5 py-px text-[10.5px] text-violet-700 dark:bg-violet-950 dark:text-violet-300">{{ row.entry.source.split('/').pop() }}</span>
              </div>
            </div>
          </div>
          <div class="absolute top-1.5 right-1.5 hidden items-center rounded-md border border-zinc-200 bg-white shadow-xs group-hover:flex dark:border-zinc-700 dark:bg-zinc-900" @click.stop>
            <button class="p-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" :title="$t('list.moveUp')" @click="moveEntry(row.entry._id, -1)"><ArrowUp class="h-3.5 w-3.5" /></button>
            <button class="p-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" :title="$t('list.moveDown')" @click="moveEntry(row.entry._id, 1)"><ArrowDown class="h-3.5 w-3.5" /></button>
            <button class="p-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100" :title="$t('list.duplicate')" @click="duplicateEntry(row.entry._id)"><Copy class="h-3.5 w-3.5" /></button>
            <button class="p-1 text-zinc-500 hover:text-red-600" :title="$t('list.delete')" @click="removeEntry(row.entry._id)"><Trash class="h-3.5 w-3.5" /></button>
          </div>
        </div>
      </template>
    </div>
    <p v-if="store.previewError" class="border-t border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
      {{ store.previewError }}
    </p>
  </template>

  <div v-else class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
    <p v-if="!store.notes.length" class="mt-6 text-center text-sm text-zinc-500">{{ $t('list.noNotes') }}</p>
    <ul v-else class="space-y-2">
      <li v-for="(n, k) in store.notes" :key="k" class="rounded-lg border border-zinc-200 px-3 py-2 text-[13px] dark:border-zinc-800">
        <span v-if="noteSource(n)" class="mono mb-1 block text-[11px] text-violet-600 dark:text-violet-400">{{ noteSource(n) }}</span>
        {{ translateMessage(n) }}
      </li>
    </ul>
  </div>
</template>
