// App-wide state: the open PDF, the config being edited (with live preview), dialogs and toasts.
import { reactive, watch } from 'vue'
import {
  api,
  ApiError,
  type ApplyResult,
  type Config,
  type Entry,
  type EntryPreview,
  type FileKind,
  type Message,
  type Meta,
  type PdfInfo,
  type Preview,
  type Settings,
  type Status,
  type Style,
  type Suggestion,
  type TexImportResult,
  type TexSource,
} from './api'
import { browserLanguage, i18n, setLanguage } from './i18n'
import { setTheme } from './theme'

const t = (key: string, params?: Record<string, unknown>) => (params ? i18n.global.t(key, params) : i18n.global.t(key))

/** Built-in values of every style field (notepdf/config.py: Style). */
export const BUILTIN: Required<Style> = {
  type: 'highlight',
  color: 'yellow',
  opacity: 0.4,
  author: '',
  subject: 'NotePDF',
  match: 'normalized',
  case_sensitive: false,
  whole_word: false,
  occurrence: 'first',
  popup: 'closed',
  sticky_note: false,
  continuation_comment: 'none',
  sequential: false,
  fuzzy_fallback: false,
  split_fallback: false,
  fuzzy_threshold: 90,
}

export interface ToastAction {
  label: string
  run: () => void
}

export interface Toast {
  id: number
  message: string
  kind: 'info' | 'success' | 'error'
  actions?: ToastAction[]
}

interface ConfirmRequest {
  message: string
  confirmLabel?: string
  danger?: boolean
  resolve: (ok: boolean) => void
}

export interface FileRequest {
  kind: FileKind
  mode: 'open' | 'save'
  suggested?: string
  resolve: (path: string | null) => void
}

interface PasswordRequest {
  path: string
  wrong: boolean
  resolve: (password: string | null) => void
}

function emptyConfig(): Config {
  return { defaults: {}, annotations: [], remove_existing: true }
}

export const store = reactive({
  ready: false,
  loadError: '',
  meta: null as Meta | null,
  settings: { language: null, theme: 'system', recent: [] } as Settings,

  config: emptyConfig(),
  configPath: null as string | null,
  dirty: false,
  pdf: null as PdfInfo | null,
  opening: false,

  preview: {} as Record<string, EntryPreview>,
  previewing: false,
  previewError: '',
  notes: [] as Message[],

  selected: null as string | null,
  rightTab: 'entry' as 'entry' | 'document',
  leftTab: 'entries' as 'entries' | 'notes',
  filter: 'all' as 'all' | 'missing' | 'warning',
  zoom: 'fit' as number | 'fit',
  focus: null as { page: number; rect: number[]; nonce: number } | null,

  applying: false,
  lastOutput: null as string | null,

  toasts: [] as Toast[],
  confirm: null as ConfirmRequest | null,
  fileRequest: null as FileRequest | null,
  passwordRequest: null as PasswordRequest | null,
  texDialog: null as TexSource | null,
  settingsDialog: false,
})

// ---- toasts & dialogs ---------------------------------------------------------------------------

let toastId = 0
export function toast(message: string, kind: Toast['kind'] = 'info', actions?: ToastAction[]): void {
  const id = ++toastId
  store.toasts.push({ id, message, kind, actions })
  const ms = actions?.length ? 9000 : kind === 'error' ? 7000 : 3500
  setTimeout(() => dismissToast(id), ms)
}

export function dismissToast(id: number): void {
  store.toasts = store.toasts.filter((x) => x.id !== id)
}

export function confirmDialog(message: string, options: { confirmLabel?: string; danger?: boolean } = {}): Promise<boolean> {
  return new Promise((resolve) => (store.confirm = { message, ...options, resolve }))
}

function askPassword(path: string, wrong: boolean): Promise<string | null> {
  return new Promise((resolve) => (store.passwordRequest = { path, wrong, resolve }))
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

// ---- startup & settings -------------------------------------------------------------------------

export async function startApp(): Promise<void> {
  const [meta, settings] = await Promise.all([api<Meta>('/api/meta'), api<Settings>('/api/settings')])
  store.meta = meta
  store.settings = settings
  store.ready = true
  if (meta.initial) await openPath(meta.initial.path, meta.initial.kind)
}

watch(() => store.settings.language, (lang) => setLanguage(lang ?? browserLanguage()), { immediate: true })
watch(() => store.settings.theme, (theme) => setTheme(theme ?? 'system'), { immediate: true })

export async function saveSettings(patch: Partial<Settings>): Promise<void> {
  Object.assign(store.settings, patch)
  try {
    store.settings = await api<Settings>('/api/settings', { method: 'PUT', json: patch })
  } catch (e) {
    toast(errorText(e), 'error')
  }
}

async function refreshRecent(): Promise<void> {
  try {
    store.settings.recent = (await api<Settings>('/api/settings')).recent
  } catch {
    /* not important */
  }
}

// ---- config helpers -----------------------------------------------------------------------------

let idCounter = 0
const newId = () => `e${++idCounter}`

function withIds(rows: Omit<Entry, '_id'>[]): Entry[] {
  return rows.map((r) => ({ ...r, _id: newId() }))
}

/** The config as the backend expects it (no client-only fields, the open PDF as input). */
export function serverConfig(): Record<string, unknown> {
  const cfg = JSON.parse(JSON.stringify(store.config)) as Config
  const annotations = cfg.annotations.map(({ _id, ...rest }) => (void _id, rest))
  return { ...cfg, input: store.pdf?.path ?? cfg.input, annotations }
}

/** The value a style field has for an entry: its own, else the document default, else the built-in one. */
export function effective<K extends keyof Style>(entry: Entry | null, key: K): Required<Style>[K] {
  const own = entry?.[key]
  if (own !== undefined && own !== null && own !== '') return own as Required<Style>[K]
  const doc = store.config.defaults[key]
  if (doc !== undefined && doc !== null && doc !== '') return doc as Required<Style>[K]
  return BUILTIN[key]
}

export function selectedEntry(): Entry | null {
  return store.config.annotations.find((e) => e._id === store.selected) ?? null
}

export function entryStatus(id: string): Status | 'pending' {
  return store.preview[id]?.status ?? 'pending'
}

export function displayText(e: Entry): string {
  if (e.regex !== undefined) return `/${e.regex}/`
  return (e.text ?? '').replace(/\{\{\s*gap[^}]*\}\}/g, '…')
}

// ---- loading guard: changes made while loading don't count as edits ------------------------------

let loading = 0
async function quietly<T>(fn: () => Promise<T> | T): Promise<T> {
  loading++
  try {
    return await fn()
  } finally {
    setTimeout(() => loading--, 0)
  }
}

watch(
  () => store.config,
  () => {
    if (!loading) store.dirty = true
    schedulePreview()
  },
  { deep: true },
)

// ---- files --------------------------------------------------------------------------------------

export function kindOf(path: string): FileKind | null {
  const ext = path.split('.').pop()?.toLowerCase()
  if (ext === 'pdf') return 'pdf'
  if (ext === 'tex') return 'tex'
  if (ext === 'yaml' || ext === 'yml' || ext === 'json') return 'config'
  return null
}

export async function openPath(path: string, kind: FileKind | null = kindOf(path)): Promise<void> {
  if (kind === 'pdf') return openPdf(path)
  if (kind === 'config') return openConfig(path)
  if (kind === 'tex') {
    store.texDialog = { ...(store.config.tex_source ?? { markers: [{ color: 'revcolor' }] }), main: path }
    return
  }
  toast(t('files.unsupported', { name: path.split('/').pop() }), 'error')
}

export async function openPdf(path: string, password?: string): Promise<void> {
  store.opening = true
  try {
    const info = await api<PdfInfo>('/api/pdf/open', { method: 'POST', json: { path, password } })
    await quietly(() => {
      store.pdf = info
      if (store.config.input !== info.path) store.config.input = info.path
      if (password) store.config.password = password
    })
    store.preview = {}
    schedulePreview(0)
    refreshRecent()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      const pw = await askPassword(path, password !== undefined)
      if (pw !== null) return openPdf(path, pw)
      return
    }
    toast(errorText(e), 'error')
  } finally {
    store.opening = false
  }
}

export async function openConfig(path: string): Promise<void> {
  if (store.dirty && store.config.annotations.length && !(await confirmDialog(t('files.discard'), { confirmLabel: t('files.discardConfirm'), danger: true })))
    return
  try {
    const res = await api<{ path: string; config: Config; converted: boolean; notes: Message[] }>('/api/config/load', { method: 'POST', json: { path } })
    await quietly(() => {
      store.config = { ...emptyConfig(), ...res.config, defaults: res.config.defaults ?? {}, annotations: withIds(res.config.annotations ?? []) }
      store.configPath = res.path
      store.selected = null
      store.notes = res.notes
      store.preview = {}
    })
    store.dirty = false
    if (res.converted) toast(t('files.converted'), 'info')
    if (store.config.input) await openPdf(store.config.input, store.config.password)
    refreshRecent()
  } catch (e) {
    toast(errorText(e), 'error')
  }
}

export async function saveConfig(path: string): Promise<boolean> {
  try {
    const res = await api<{ path: string }>('/api/config/save', { method: 'POST', json: { path, config: serverConfig() } })
    store.configPath = res.path
    store.dirty = false
    toast(t('files.configSaved', { path: res.path }), 'success')
    refreshRecent()
    return true
  } catch (e) {
    toast(errorText(e), 'error')
    return false
  }
}

export async function newConfig(): Promise<void> {
  if (store.dirty && store.config.annotations.length && !(await confirmDialog(t('files.discard'), { confirmLabel: t('files.discardConfirm'), danger: true })))
    return
  await quietly(() => {
    store.config = { ...emptyConfig(), input: store.pdf?.path }
    store.configPath = null
    store.selected = null
    store.notes = []
    store.preview = {}
  })
  store.dirty = false
}

export async function openExternal(path: string, reveal = false): Promise<void> {
  try {
    await api('/api/open', { method: 'POST', json: { path, reveal } })
  } catch (e) {
    toast(errorText(e), 'error')
  }
}

// ---- entries ------------------------------------------------------------------------------------

export function addEntry(fields: Omit<Partial<Entry>, '_id'>, select = true): Entry {
  const entry: Entry = { _id: newId(), text: '', ...fields }
  const sel = store.config.annotations.findIndex((e) => e._id === store.selected)
  store.config.annotations.splice(sel >= 0 && !fields.text ? sel + 1 : store.config.annotations.length, 0, entry)
  if (select) selectEntry(entry._id)
  return entry
}

export function removeEntry(id: string): void {
  const i = store.config.annotations.findIndex((e) => e._id === id)
  if (i < 0) return
  store.config.annotations.splice(i, 1)
  if (store.selected === id) store.selected = store.config.annotations[i]?._id ?? store.config.annotations[i - 1]?._id ?? null
}

export function duplicateEntry(id: string): void {
  const i = store.config.annotations.findIndex((e) => e._id === id)
  if (i < 0) return
  const copy = { ...JSON.parse(JSON.stringify(store.config.annotations[i])), _id: newId() }
  store.config.annotations.splice(i + 1, 0, copy)
  selectEntry(copy._id)
}

export function moveEntry(id: string, delta: number): void {
  const list = store.config.annotations
  const i = list.findIndex((e) => e._id === id)
  const j = i + delta
  if (i < 0 || j < 0 || j >= list.length) return
  ;[list[i], list[j]] = [list[j], list[i]]
}

export function selectEntry(id: string | null, scroll = true): void {
  store.selected = id
  if (id) {
    store.rightTab = 'entry'
    if (scroll) focusEntry(id)
  }
}

export function focusEntry(id: string): void {
  const hit = store.preview[id]?.hits[0]
  if (hit) store.focus = { page: hit.page, rect: hit.rects[0], nonce: Date.now() }
}

/** Turn a word selection on a page into an entry that targets exactly that occurrence. */
export async function addFromSelection(page: number, first: number, last: number, extra: Omit<Partial<Entry>, '_id'>): Promise<void> {
  try {
    const s = await api<Suggestion>('/api/pdf/selection', {
      method: 'POST',
      json: { page, first, last, defaults: serverConfig().defaults },
    })
    const fields: Omit<Partial<Entry>, '_id'> = { text: s.text, ...extra }
    if (s.pages !== undefined) fields.pages = s.pages
    if (s.occurrence !== undefined) fields.occurrence = s.occurrence
    const added = addEntry(fields, false)
    store.selected = added._id
    store.rightTab = 'entry'
  } catch (e) {
    toast(errorText(e), 'error')
  }
}

// ---- preview ------------------------------------------------------------------------------------

let previewTimer: ReturnType<typeof setTimeout> | undefined
let previewSeq = 0

export function schedulePreview(delay = 350): void {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(runPreview, delay)
}

async function runPreview(): Promise<void> {
  if (!store.pdf) return
  const ids = store.config.annotations.map((e) => e._id)
  const seq = ++previewSeq
  store.previewing = true
  try {
    const res = await api<Preview>('/api/preview', { method: 'POST', json: { config: serverConfig() } })
    if (seq !== previewSeq) return // a newer preview is on its way
    const map: Record<string, EntryPreview> = {}
    res.entries.forEach((p, i) => (map[ids[i]] = p))
    store.preview = map
    store.previewError = ''
  } catch (e) {
    if (seq === previewSeq) store.previewError = errorText(e)
  } finally {
    if (seq === previewSeq) store.previewing = false
  }
}

export function previewCounts(): Record<Status, number> {
  const counts: Record<Status, number> = { found: 0, warning: 0, missing: 0, invalid: 0 }
  for (const e of store.config.annotations) {
    const s = store.preview[e._id]?.status
    if (s) counts[s]++
  }
  return counts
}

// ---- saving the PDF -----------------------------------------------------------------------------

export async function applyPdf(output?: string): Promise<void> {
  if (!store.pdf) return
  store.applying = true
  try {
    const res = await api<ApplyResult>('/api/apply', { method: 'POST', json: { config: serverConfig(), output } })
    store.lastOutput = res.output
    const found = res.entries.filter((e) => e.status !== 'missing').length
    toast(t('apply.done', { found, total: res.entries.length, path: res.output.split('/').pop() }), 'success', [
      { label: t('apply.open'), run: () => openExternal(res.output) },
      { label: t('apply.reveal'), run: () => openExternal(res.output, true) },
    ])
    if (res.output === store.pdf.path) await openPdf(store.pdf.path, store.config.password)
  } catch (e) {
    toast(errorText(e), 'error')
  } finally {
    store.applying = false
  }
}

// ---- TeX import ---------------------------------------------------------------------------------

export async function importTex(tex: TexSource): Promise<boolean> {
  try {
    const res = await api<TexImportResult>('/api/tex/import', { method: 'POST', json: { tex } })
    const old = store.config.annotations.filter((e) => e.source)
    if (old.length && !(await confirmDialog(t('tex.replaceConfirm', { n: old.length }), { confirmLabel: t('tex.replace') }))) return false
    const manual = store.config.annotations.filter((e) => !e.source)
    store.config.annotations = [...manual, ...withIds(res.rows)]
    store.config.tex_source = res.tex_source
    for (const [k, v] of Object.entries(res.defaults) as [keyof Style, never][]) {
      if (store.config.defaults[k] === undefined) store.config.defaults[k] = v
    }
    store.notes = res.notes
    store.selected = null
    store.leftTab = 'entries'
    toast(t('tex.imported', { entries: res.rows.length, markers: res.markers, notes: res.notes.length }), res.rows.length ? 'success' : 'info')
    if (!store.pdf) toast(t('tex.openPdfHint'), 'info')
    return true
  } catch (e) {
    toast(errorText(e), 'error')
    return false
  }
}

window.addEventListener('beforeunload', (event) => {
  if (store.dirty && store.config.annotations.length) event.preventDefault()
})
