<script setup lang="ts">
import { Info } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AnnotType } from '../api'
import { cssColor } from '../colors'
import { effective, store } from '../store'
import type { OverlayHit } from '../overlay'
import PageView from './PageView.vue'

const container = ref<HTMLElement>()
const width = ref(900)
let observer: ResizeObserver | undefined

const pages = computed(() => store.pdf?.pages ?? [])
const fitScale = computed(() => {
  const widest = Math.max(1, ...pages.value.map((p) => p.width))
  return Math.min(4, Math.max(0.25, (width.value - 56) / widest))
})
const scale = computed(() => (store.zoom === 'fit' ? fitScale.value : store.zoom))

const hitsByPage = computed(() => {
  const out: Record<number, OverlayHit[]> = {}
  for (const entry of store.config.annotations) {
    const preview = store.preview[entry._id]
    if (!preview) continue
    const color = cssColor(effective(entry, 'color')) ?? '#FFEB3B'
    const opacity = Number(effective(entry, 'opacity'))
    const type = effective(entry, 'type') as AnnotType
    for (const hit of preview.hits) {
      ;(out[hit.page] ??= []).push({
        id: entry._id,
        rects: hit.rects,
        color,
        opacity,
        type,
        selected: entry._id === store.selected,
        comment: entry.comment,
      })
    }
  }
  // Draw the selected entry last so its outline is on top.
  for (const list of Object.values(out)) list.sort((a, b) => Number(a.selected) - Number(b.selected))
  return out
})

watch(
  () => store.focus,
  async (focus) => {
    if (!focus || !container.value) return
    await nextTick()
    const el = container.value.querySelector<HTMLElement>(`[data-page="${focus.page}"]`)
    if (!el) return
    const [x0, y0] = focus.rect
    container.value.scrollTo({
      top: Math.max(0, el.offsetTop + y0 * scale.value - container.value.clientHeight * 0.3),
      left: Math.max(0, el.offsetLeft + x0 * scale.value - container.value.clientWidth * 0.3),
      behavior: 'smooth',
    })
  },
)

function onWheel(e: WheelEvent) {
  if (!(e.ctrlKey || e.metaKey)) return
  e.preventDefault()
  const next = scale.value * (e.deltaY < 0 ? 1.1 : 1 / 1.1)
  store.zoom = Math.min(4, Math.max(0.25, Math.round(next * 100) / 100))
}

onMounted(() => {
  if (!container.value) return
  observer = new ResizeObserver(([e]) => (width.value = e.contentRect.width))
  observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="container" class="absolute inset-0 overflow-auto" :data-fit-scale="fitScale.toFixed(3)" @wheel="onWheel">
    <div v-if="store.pdf?.existing" class="sticky top-0 left-0 z-10 flex justify-center px-4 pt-3">
      <div class="flex items-center gap-2 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-800 shadow-sm dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
        <Info class="h-3.5 w-3.5" />{{ $t('viewer.existing', { n: store.pdf.existing }) }}
      </div>
    </div>
    <div class="flex min-w-max flex-col items-center gap-5 px-7 py-6">
      <PageView
        v-for="(p, i) in pages"
        :key="`${store.pdf?.version}-${i}`"
        :index="i"
        :page="p"
        :scale="scale"
        :hits="hitsByPage[i] ?? []"
      />
    </div>
  </div>
</template>
