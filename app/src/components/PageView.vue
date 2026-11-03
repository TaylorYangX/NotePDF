<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, apiUrl, type Word } from '../api'
import type { OverlayHit } from '../overlay'
import { selectEntry, store } from '../store'
import SelectionToolbar from './SelectionToolbar.vue'

const props = defineProps<{ index: number; page: { width: number; height: number }; scale: number; hits: OverlayHit[] }>()

const root = ref<HTMLElement>()
const visible = ref(false)
const loaded = ref(false)
const words = ref<Word[] | null>(null)
let io: IntersectionObserver | undefined

const w = computed(() => props.page.width * props.scale)
const h = computed(() => props.page.height * props.scale)
// Render a little sharper than displayed (HiDPI screens); bucketed so zooming reuses cached images.
const renderScale = computed(() => Math.min(4, Math.ceil(props.scale * (window.devicePixelRatio || 1) * 2) / 2))
const src = computed(() => apiUrl(`/api/pdf/page/${props.index}.png?scale=${renderScale.value}&v=${store.pdf?.version ?? ''}`))

onMounted(() => {
  io = new IntersectionObserver(
    ([e]) => {
      if (e.isIntersecting && !visible.value) {
        visible.value = true
        loadWords()
      }
    },
    { rootMargin: '800px 0px' },
  )
  if (root.value) io.observe(root.value)
})
onBeforeUnmount(() => {
  io?.disconnect()
  stopDrag()
})

async function loadWords() {
  try {
    words.value = (await api<{ words: Word[] }>(`/api/pdf/page/${props.index}/words`)).words
  } catch {
    words.value = []
  }
}

// ---- selecting words, like a PDF viewer --------------------------------------------------------

const anchor = ref(-1)
const focusIdx = ref(-1)
const dragging = ref(false)
const showToolbar = ref(false)
const hover = ref<{ hit: OverlayHit; x: number; y: number } | null>(null)
let downAt: { x: number; y: number } | null = null
let moved = false

const range = computed<[number, number] | null>(() =>
  anchor.value < 0 || focusIdx.value < 0 ? null : [Math.min(anchor.value, focusIdx.value), Math.max(anchor.value, focusIdx.value)],
)
const selectedRects = computed(() => (range.value && words.value ? words.value.slice(range.value[0], range.value[1] + 1).map((wd) => wd.rect) : []))
const toolbarAt = computed(() => {
  const last = selectedRects.value[selectedRects.value.length - 1]
  if (!last) return null
  const below = last[3] * props.scale + 8
  return { x: Math.min(Math.max(8, last[0] * props.scale - 40), w.value - 330), y: below + 150 > h.value ? last[1] * props.scale - 150 : below }
})

function pdfPoint(e: MouseEvent): { x: number; y: number } {
  const box = root.value!.getBoundingClientRect()
  return { x: (e.clientX - box.left) / props.scale, y: (e.clientY - box.top) / props.scale }
}

function wordAt(p: { x: number; y: number }, nearest: boolean): number {
  const list = words.value ?? []
  let best = -1
  let bestD = nearest ? Infinity : 4 // a few points of slack around words
  list.forEach((wd, i) => {
    const [x0, y0, x1, y1] = wd.rect
    const dx = p.x < x0 ? x0 - p.x : p.x > x1 ? p.x - x1 : 0
    const dy = p.y < y0 ? y0 - p.y : p.y > y1 ? p.y - y1 : 0
    const d = dx + dy * 3 // prefer the same line
    if (d < bestD) {
      bestD = d
      best = i
    }
  })
  return best
}

function hitAt(p: { x: number; y: number }): OverlayHit | null {
  for (let k = props.hits.length - 1; k >= 0; k--) {
    const hit = props.hits[k]
    if (hit.rects.some(([x0, y0, x1, y1]) => p.x >= x0 && p.x <= x1 && p.y >= y0 - 1 && p.y <= y1 + 1)) return hit
  }
  return null
}

function onDown(e: MouseEvent) {
  if (e.button !== 0) return
  const p = pdfPoint(e)
  downAt = p
  moved = false
  showToolbar.value = false
  const idx = wordAt(p, false)
  anchor.value = idx
  focusIdx.value = idx
  dragging.value = true
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', onUp)
}

function onDrag(e: MouseEvent) {
  if (!dragging.value) return
  const p = pdfPoint(e)
  if (downAt && Math.hypot(p.x - downAt.x, p.y - downAt.y) * props.scale > 4) moved = true
  if (!moved) return
  if (anchor.value < 0) anchor.value = wordAt(downAt ?? p, true)
  focusIdx.value = wordAt(p, true)
}

function onUp(e: MouseEvent) {
  stopDrag()
  const p = pdfPoint(e)
  if (!moved) {
    anchor.value = focusIdx.value = -1
    const hit = hitAt(p)
    selectEntry(hit ? hit.id : null, false)
    return
  }
  showToolbar.value = range.value !== null
}

function onDouble(e: MouseEvent) {
  const idx = wordAt(pdfPoint(e), false)
  if (idx < 0) return
  anchor.value = focusIdx.value = idx
  showToolbar.value = true
}

function stopDrag() {
  dragging.value = false
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', onUp)
}

function onHover(e: MouseEvent) {
  if (dragging.value) return
  const p = pdfPoint(e)
  const hit = hitAt(p)
  hover.value = hit ? { hit, x: p.x * props.scale, y: p.y * props.scale } : null
}

function clearSelection() {
  anchor.value = focusIdx.value = -1
  showToolbar.value = false
}

// ---- drawing ------------------------------------------------------------------------------------

function squiggle([x0, , x1, y1]: number[]): string {
  const step = 2
  let d = `M ${x0} ${y1 - 1}`
  for (let x = x0, up = true; x < x1; x += step, up = !up) d += ` L ${Math.min(x + step, x1)} ${y1 - (up ? 2.2 : 0.6)}`
  return d
}
</script>

<template>
  <div
    ref="root"
    :data-page="index"
    class="relative shrink-0 bg-white shadow-md ring-1 ring-black/5 select-none"
    :style="{ width: `${w}px`, height: `${h}px`, cursor: hover ? 'pointer' : 'text' }"
    @mousedown="onDown"
    @mousemove="onHover"
    @mouseleave="hover = null"
    @dblclick="onDouble"
  >
    <img
      v-if="visible"
      :src="src"
      alt=""
      draggable="false"
      class="pointer-events-none absolute inset-0 h-full w-full"
      :class="loaded ? '' : 'opacity-0'"
      @load="loaded = true"
    />
    <div v-if="!loaded" class="absolute inset-0 animate-pulse bg-zinc-100" />

    <svg class="pointer-events-none absolute inset-0 h-full w-full" :viewBox="`0 0 ${page.width} ${page.height}`" preserveAspectRatio="none">
      <g v-for="(hit, k) in hits" :key="`${hit.id}-${k}`">
        <template v-for="(r, j) in hit.rects" :key="j">
          <rect
            v-if="hit.type === 'highlight'"
            :x="r[0]" :y="r[1]" :width="r[2] - r[0]" :height="r[3] - r[1]"
            :fill="hit.color" :fill-opacity="hit.opacity" style="mix-blend-mode: multiply"
          />
          <line v-else-if="hit.type === 'underline'" :x1="r[0]" :x2="r[2]" :y1="r[3] - 0.8" :y2="r[3] - 0.8" :stroke="hit.color" stroke-width="1.2" />
          <line v-else-if="hit.type === 'strikeout'" :x1="r[0]" :x2="r[2]" :y1="(r[1] + r[3]) / 2" :y2="(r[1] + r[3]) / 2" :stroke="hit.color" stroke-width="1.2" />
          <path v-else :d="squiggle(r)" fill="none" :stroke="hit.color" stroke-width="0.9" />
          <rect
            v-if="hit.selected"
            :x="r[0] - 1" :y="r[1] - 1" :width="r[2] - r[0] + 2" :height="r[3] - r[1] + 2" rx="1.5"
            fill="none" stroke="#6366f1" stroke-width="1.6" vector-effect="non-scaling-stroke"
          />
        </template>
      </g>
      <rect
        v-for="(r, k) in selectedRects"
        :key="`sel-${k}`"
        :x="r[0]" :y="r[1]" :width="r[2] - r[0]" :height="r[3] - r[1]"
        fill="#3b82f6" fill-opacity="0.28"
      />
    </svg>

    <div
      v-if="hover && hover.hit.comment && !showToolbar"
      class="pointer-events-none absolute z-10 max-w-72 rounded-lg bg-zinc-900/95 px-2.5 py-1.5 text-xs leading-snug whitespace-pre-wrap text-white shadow-lg"
      :style="{ left: `${Math.min(hover.x + 12, w - 200)}px`, top: `${hover.y + 16}px` }"
    >
      {{ hover.hit.comment }}
    </div>

    <SelectionToolbar
      v-if="showToolbar && toolbarAt && range"
      :x="toolbarAt.x"
      :y="toolbarAt.y"
      :page="index"
      :range="range"
      @done="clearSelection"
      @mousedown.stop
    />
  </div>
</template>
