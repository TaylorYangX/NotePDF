// Highlight colors, kept in step with notepdf/colors.py.
import type { ColorValue } from './api'

export const NAMED_COLORS: Record<string, string> = {
  yellow: '#FFEB3B',
  green: '#8BC34A',
  blue: '#64B5F6',
  cyan: '#4DD0E1',
  pink: '#F48FB1',
  red: '#EF5350',
  orange: '#FFB74D',
  purple: '#BA68C8',
  gray: '#BDBDBD',
  grey: '#BDBDBD',
  black: '#000000',
  white: '#FFFFFF',
}

export const SWATCHES = ['yellow', 'green', 'blue', 'pink', 'orange', 'purple', 'cyan', 'red']

/** CSS hex for any color the config accepts, or null if it isn't one. */
export function cssColor(value: ColorValue | undefined | null): string | null {
  if (value === undefined || value === null || value === '') return null
  if (Array.isArray(value)) {
    if (value.length !== 3) return null
    const scale = value.some((v) => v > 1) ? 1 : 255
    return '#' + value.map((v) => Math.round(Math.max(0, Math.min(255, v * scale))).toString(16).padStart(2, '0')).join('').toUpperCase()
  }
  const s = value.trim()
  const named = NAMED_COLORS[s.toLowerCase()]
  if (named) return named
  let h = s.replace(/^#/, '')
  if (/^[0-9a-f]{3}$/i.test(h)) h = h.split('').map((c) => c + c).join('')
  return /^[0-9a-f]{6}$/i.test(h) ? `#${h.toUpperCase()}` : null
}

/** The swatch name for a value, if it is one of the named colors. */
export function colorName(value: ColorValue | undefined): string | null {
  const hex = cssColor(value)
  return SWATCHES.find((n) => NAMED_COLORS[n] === hex) ?? null
}
