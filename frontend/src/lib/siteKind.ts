import type { RoofType } from './types'

/** Site kind of a roof / terrain type – mirrors backend/app/services/site_kind.py. */
export type SiteKind = 'pitched' | 'flat' | 'ground' | 'fence'
export const SITE_KINDS: SiteKind[] = ['pitched', 'flat', 'ground', 'fence']

export function kindFromCode(code: string | null | undefined): SiteKind {
  const c = String(code || '').toLowerCase()
  if (c.startsWith('ground')) return 'ground'
  if (c.startsWith('flat')) return 'flat'
  if (c.includes('fence') || c.startsWith('wall') || c.startsWith('facade')) return 'fence'
  return 'pitched'
}

export function siteKind(code: string | null | undefined, roofTypes?: RoofType[]): SiteKind {
  const r = roofTypes?.find((x) => x.code === code)
  const k = r?.kind as SiteKind | undefined
  return k && SITE_KINDS.includes(k) ? k : kindFromCode(code)
}

export const isRoofKind = (k: SiteKind) => k === 'pitched' || k === 'flat'
