import type { AnnotType } from './api'

/** One entry's boxes on one page, as drawn over the page image. */
export interface OverlayHit {
  id: string
  rects: number[][]
  color: string
  opacity: number
  type: AnnotType
  selected: boolean
  comment?: string
}
