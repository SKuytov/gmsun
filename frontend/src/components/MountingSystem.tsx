/* AEROCOMPACT® mounting system card: technical limits + manufacturer documents for the selected roof type. */
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, FileText } from 'lucide-react'
import { get } from '@/lib/api'
import { useT } from '@/lib/i18n'

export interface MountingSystemInfo {
  code: string
  family: string
  name_bg: string
  name_en: string
  covering_bg: string
  orientation: string
  roof_pitch_deg: [number, number] | null
  distance_to_roof_mm: [number, number] | null
  wind_kn_m2: number | null
  snow_kn_m2: number | null
  frame_mm: [number, number] | null
  rails: boolean
  notes_bg: string
  docs: Record<string, string>
}

export interface MountingSystemsResponse {
  systems: MountingSystemInfo[]
  roof_system: Record<string, string>
  documents: { system: string; kind: string; url: string }[]
  doc_sets: Record<string, Record<string, string>>
}

export function useMountingSystems() {
  return useQuery({ queryKey: ['mounting-systems'], queryFn: () => get<MountingSystemsResponse>('/api/catalog/mounting/systems'), staleTime: 60 * 60 * 1000 })
}

const DOC_LABELS: Record<string, [string, string]> = {
  leaflet: ['Продуктов лист', 'Product leaflet'],
  leaflet_s05: ['Продуктов лист S05 (5°)', 'Leaflet S05 (5°)'],
  leaflet_s10: ['Продуктов лист S10 (10°)', 'Leaflet S10 (10°)'],
  leaflet_s15: ['Продуктов лист S15 (15°)', 'Leaflet S15 (15°)'],
  assembly: ['Инструкция за монтаж', 'Assembly instructions'],
  assembly_uk: ['Инструкция за монтаж (UK)', 'Assembly instructions (UK)'],
  checklist: ['Чеклист за монтаж', 'Installation checklist'],
  product: ['Продуктова страница', 'Product page'],
  tile_compatibility: ['Съвместимост с керемиди', 'Tile compatibility'],
  friction_test: ['Тест на триене (баласт)', 'Friction test (ballast)'],
  manual_us: ['Ръководство (US)', 'Manual (US)'],
  planning: ['Планиране', 'Planning guide'],
}
const docLabel = (k: string, lang: string) => (DOC_LABELS[k] ? DOC_LABELS[k][lang === 'bg' ? 0 : 1] : k.replace(/_/g, ' '))

const range = (r: [number, number] | null | undefined, unit: string) => (r ? `${r[0]}–${r[1]}${unit === '°' ? '' : ' '}${unit}` : '—')

export function DocLinks({ docs, compact }: { docs: Record<string, string>; compact?: boolean }) {
  const { lang } = useT()
  return (
    <div className={compact ? 'flex flex-wrap gap-1' : 'flex flex-wrap gap-1.5'}>
      {Object.entries(docs).map(([k, url]) => (
        <a key={k} href={url} target="_blank" rel="noreferrer" className="btn-ghost btn-sm" data-testid={`link-doc-${k}`}>
          {url.toLowerCase().endsWith('.pdf') ? <FileText className="h-3.5 w-3.5" /> : <ExternalLink className="h-3.5 w-3.5" />} {docLabel(k, lang)}
        </a>
      ))}
    </div>
  )
}

/** Card for the system mapped to `roofType` (nothing rendered for generic/unknown roof types). */
export function MountingSystemCard({ roofType, className }: { roofType: string; className?: string }) {
  const { t, lang } = useT()
  const q = useMountingSystems()
  const code = q.data?.roof_system[roofType]
  const sys = q.data?.systems.find((s) => s.code === code)
  if (!sys) return null
  const kv: [string, string][] = [
    [t('covering'), sys.covering_bg],
    [t('roof_pitch'), range(sys.roof_pitch_deg, '°')],
    [t('distance_to_roof'), range(sys.distance_to_roof_mm, 'mm')],
    [t('wind_load'), sys.wind_kn_m2 != null ? `${sys.wind_kn_m2} kN/m²` : '—'],
    [t('snow_load'), sys.snow_kn_m2 != null ? `${sys.snow_kn_m2} kN/m²` : '—'],
    [t('frame_height'), range(sys.frame_mm, 'mm')],
  ]
  return (
    <div className={`card p-3 ${className || ''}`} data-testid="card-mounting-system">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="text-xs uppercase tracking-wide text-ink-3">{t('mounting_system')} · AEROCOMPACT®</span>
          <h4 className="font-semibold leading-tight">{lang === 'bg' ? sys.name_bg : sys.name_en}</h4>
        </div>
        <span className="rounded bg-sun/20 px-2 py-0.5 text-xs font-medium">
          {sys.family} {sys.code}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        {kv.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-ink-3">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {sys.notes_bg && <p className="mt-2 text-xs text-ink-2">{sys.notes_bg}</p>}
      <div className="mt-2">
        <span className="mb-1 block text-xs text-ink-3">{t('mounting_docs')}</span>
        <DocLinks docs={sys.docs} />
      </div>
    </div>
  )
}
