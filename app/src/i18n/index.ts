import { createI18n } from 'vue-i18n'
import type { Message } from '../api'
import en from './en.json'
import zhCN from './zh-CN.json'

export type Language = 'en' | 'zh-CN'

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, 'zh-CN': zhCN },
})

export function setLanguage(language: Language): void {
  i18n.global.locale.value = language
  document.documentElement.lang = language
}

export function browserLanguage(): Language {
  return navigator.language.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en'
}

/** A backend message in the current language (falls back to the English text it came with). */
export function translateMessage(m: Message): string {
  if (!m.code) return m.text
  const key = `msg.${m.code}`
  const t = i18n.global.t
  const body = i18n.global.te(key) || i18n.global.te(key, 'en') ? t(key, m.params as Record<string, unknown>) : m.text.replace(/^[^:]*\.tex:\d+: /, '')
  return body
}
