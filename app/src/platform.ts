// Things the desktop app does natively, each with a browser fallback.
import { isTauri } from './api'
import type { FileKind } from './api'
import { store } from './store'

export const EXTENSIONS: Record<FileKind, string[]> = {
  pdf: ['pdf'],
  config: ['yaml', 'yml', 'json'],
  tex: ['tex'],
}

/** Ask for a file to open or a path to save to. Native dialog in the app, the in-app browser otherwise. */
export async function pickFile(kind: FileKind, mode: 'open' | 'save' = 'open', suggested?: string): Promise<string | null> {
  if (isTauri) {
    const dialog = await import('@tauri-apps/plugin-dialog')
    const filters = [{ name: kind.toUpperCase(), extensions: EXTENSIONS[kind] }]
    if (mode === 'save') return dialog.save({ filters, defaultPath: suggested })
    const chosen = await dialog.open({ multiple: false, filters, defaultPath: suggested })
    return Array.isArray(chosen) ? (chosen[0] ?? null) : chosen
  }
  return new Promise((resolve) => (store.fileRequest = { kind, mode, suggested, resolve }))
}

/** In the desktop app, call `handler` with the paths of files dropped on the window. */
export async function onAppFileDrop(handler: (paths: string[]) => void): Promise<() => void> {
  if (!isTauri) return () => {}
  const { getCurrentWebview } = await import('@tauri-apps/api/webview')
  return getCurrentWebview().onDragDropEvent((event) => {
    if (event.payload.type === 'drop') handler(event.payload.paths)
  })
}
