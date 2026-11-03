// Talks to the Python backend: the same origin in a browser, or the port the desktop app started it on.
import { invoke } from '@tauri-apps/api/core'

export const isTauri = '__TAURI_INTERNALS__' in window

let base = ''

/** Resolve where the backend lives. In the app this waits until the backend the app started is listening. */
export async function initApi(): Promise<void> {
  if (isTauri) base = await invoke<string>('backend_url')
}

export function apiUrl(path: string): string {
  return base + path
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly body: Record<string, unknown> = {}) {
    super(message)
  }
}

export async function api<T = unknown>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...init } = options
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: json === undefined ? init.headers : { 'Content-Type': 'application/json', ...init.headers },
    body: json === undefined ? init.body : JSON.stringify(json),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail
    const message = Array.isArray(detail)
      ? detail.map((e: { loc: string[]; msg: string }) => `${e.loc.filter((x) => x !== 'body').join('.')}: ${e.msg}`).join('; ')
      : String(detail || response.statusText)
    throw new ApiError(message, response.status, body as Record<string, unknown>)
  }
  return body as T
}

// ---- Types mirroring notepdf/config.py and the GUI API ------------------------------------------

export type AnnotType = 'highlight' | 'underline' | 'strikeout' | 'squiggly'
export type MatchMode = 'normalized' | 'exact' | 'fuzzy'
export type Occurrence = 'first' | 'all' | number | number[]
export type ColorValue = string | number[]
export type PagesValue = number | string | (number | string)[]

/** Settings that `defaults` provides and any entry may override (all optional here). */
export interface Style {
  type?: AnnotType
  color?: ColorValue
  opacity?: number
  author?: string
  subject?: string
  match?: MatchMode
  case_sensitive?: boolean
  whole_word?: boolean
  occurrence?: Occurrence
  popup?: 'closed' | 'open' | 'none'
  sticky_note?: boolean
  continuation_comment?: string
  sequential?: boolean
  fuzzy_fallback?: boolean
  split_fallback?: boolean
  fuzzy_threshold?: number
}

export interface Entry extends Style {
  _id: string // client-only key, stripped before sending
  text?: string
  regex?: string
  comment?: string
  pages?: PagesValue
  context_before?: string
  context_after?: string
  text_color?: ColorValue
  group?: string
  source?: string
  required?: boolean
}

export interface MarkerSpec {
  color?: string
  macro?: string
  env?: string
  highlight?: string
  comment?: string
}

export interface TexSource {
  main: string
  markers: MarkerSpec[]
  detect_macros?: boolean
  replacements?: Record<string, string>
  include_captions?: boolean
  include_footnotes?: boolean
  min_segment_chars?: number
}

export interface Config {
  input?: string
  output?: string
  password?: string
  remove_existing?: boolean
  defaults: Style
  annotations: Entry[]
  tex_source?: TexSource
}

export interface PdfInfo {
  path: string
  name: string
  version: string
  existing: number
  encrypted: boolean
  pages: { width: number; height: number; rotation: number }[]
}

export interface Message {
  code: string | null
  params: Record<string, string | number>
  text: string
}

export type Status = 'found' | 'warning' | 'missing' | 'invalid'

export interface Hit {
  page: number
  rects: [number, number, number, number][]
}

export interface EntryPreview {
  index: number
  status: Status
  error?: string
  warnings: Message[]
  modes?: string[]
  score?: number | null
  hits: Hit[]
}

export interface Preview {
  version: string
  entries: EntryPreview[]
  counts: Record<Status, number>
}

export interface Word {
  text: string
  rect: [number, number, number, number]
}

export interface Suggestion {
  text: string
  pages?: number
  occurrence?: number
  matches: number
}

export interface Meta {
  version: string
  wsl: boolean
  home: string
  cwd: string
  app_mode: boolean
  initial: { path: string; kind: FileKind } | null
  fuzzy: boolean
}

export type FileKind = 'pdf' | 'config' | 'tex'

export interface RecentFile {
  path: string
  kind: FileKind
  opened: number
}

export interface Settings {
  language: 'en' | 'zh-CN' | null
  theme: 'system' | 'light' | 'dark'
  recent: RecentFile[]
}

export interface FsEntry {
  name: string
  path: string
  kind: 'dir' | 'file'
  size: number | null
  mtime: number
}

export interface FsListing {
  path: string
  parent: string | null
  entries: FsEntry[]
  roots: { name: string; path: string }[]
}

export interface ApplyResult {
  output: string
  removed: number
  entries: { index: number; status: Status; pages: number[] }[]
  notes: Message[]
}

export interface TexImportResult {
  rows: Omit<Entry, '_id'>[]
  notes: Message[]
  markers: number
  tex_source: TexSource
  defaults: Style
}
