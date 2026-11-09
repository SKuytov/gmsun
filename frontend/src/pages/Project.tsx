import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Loading, Select, cx, useToast } from '@/components/ui'
import { errMsg, get, patch } from '@/lib/api'
import { fmtNum, useT, type Key } from '@/lib/i18n'
import type { CatalogItem, LaborOption, PricingSettings, Project, RoofType, Selections } from '@/lib/types'
import { ClientStep, ParamsStep } from './steps/ClientParams'
import { EquipmentStep } from './steps/Equipment'
import { LaborStep, MaterialsStep } from './steps/Materials'
import { LayoutStep } from './steps/LayoutStep'
import { QuoteStep } from './steps/QuoteStep'
import { OrdersStep } from './steps/OrdersStep'
import { DocumentsStep } from './steps/DocumentsStep'

export const STEPS = ['client', 'params', 'layout', 'equipment', 'materials', 'labor', 'quote', 'orders', 'documents'] as const
export type Step = (typeof STEPS)[number]

export interface StepCtx {
  project: Project
  sel: Selections
  setSel: (patch: Partial<Selections>) => void
  /** Replace the local selections with the ones the server already stored (no PATCH). */
  replaceSel: (s: Selections) => void
  update: (patch: Partial<Project>) => Promise<void>
  items: CatalogItem[]
  roofTypes: RoofType[]
  labor: LaborOption[]
  pricing: PricingSettings
  panelQty: number
  kwp: number
}

export function useCatalog() {
  const items = useQuery({ queryKey: ['catalog', 'items'], queryFn: () => get<CatalogItem[]>('/api/catalog/items') })
  const roofTypes = useQuery({ queryKey: ['roof-types'], queryFn: () => get<RoofType[]>('/api/catalog/roof-types') })
  const labor = useQuery({ queryKey: ['labor'], queryFn: () => get<LaborOption[]>('/api/catalog/labor') })
  const pricing = useQuery({ queryKey: ['settings', 'pricing'], queryFn: () => get<{ value: PricingSettings }>('/api/settings/pricing') })
  return { items, roofTypes, labor, pricing }
}

export default function ProjectPage() {
  const { id, step: stepParam } = useParams()
  const pid = Number(id)
  const step: Step = (STEPS as readonly string[]).includes(stepParam || '') ? (stepParam as Step) : 'client'
  const nav = useNavigate()
  const { t, lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()

  const project = useQuery({ queryKey: ['project', pid], queryFn: () => get<Project>(`/api/projects/${pid}`), enabled: !!pid })
  const { items, roofTypes, labor, pricing } = useCatalog()

  // selections draft persisted in project.params.selections
  const [sel, setSelState] = useState<Selections>({})
  const loaded = useRef(false)
  // local edits not yet confirmed by the server; while there are none, the local draft follows the server copy
  // (quote-level edits and one-click fixes are written back into the project selections by the server)
  const editSeq = useRef(0)
  const savedSeq = useRef(0)
  useEffect(() => {
    if (!project.data) return
    if (!loaded.current || editSeq.current === savedSeq.current) {
      setSelState((project.data.params?.selections as Selections) || {})
      loaded.current = true
    }
  }, [project.data])

  const saveSel = useMutation({
    mutationFn: async ({ s, seq }: { s: Selections; seq: number }) => {
      const res = await patch<Project>(`/api/projects/${pid}`, { params: { ...(project.data?.params || {}), selections: s } })
      savedSeq.current = Math.max(savedSeq.current, seq)
      return res
    },
    onSuccess: (p) => {
      qc.setQueryData(['project', pid], p)
      // the server re-prices the working (draft) quote on every change -> refresh it everywhere
      qc.invalidateQueries({ queryKey: ['quotes', pid] })
      qc.invalidateQueries({ queryKey: ['compat', pid] })
    },
    onError: (e, v) => {
      savedSeq.current = Math.max(savedSeq.current, v.seq) // keep the local draft, but let the server copy win again
      toast.push(errMsg(e), 'bad')
    },
  })
  const timer = useRef<number | undefined>(undefined)
  const setSel = useCallback(
    (p: Partial<Selections>) => {
      setSelState((prev) => {
        const next = { ...prev, ...p }
        const seq = ++editSeq.current
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => saveSel.mutate({ s: next, seq }), 600)
        return next
      })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pid],
  )

  const replaceSel = useCallback((s: Selections) => {
    window.clearTimeout(timer.current)
    savedSeq.current = editSeq.current
    setSelState(s || {})
  }, [])

  const update = useCallback(
    async (p: Partial<Project>) => {
      try {
        const res = await patch<Project>(`/api/projects/${pid}`, p)
        qc.setQueryData(['project', pid], res)
        qc.invalidateQueries({ queryKey: ['projects'] })
        qc.invalidateQueries({ queryKey: ['quotes', pid] })
        qc.invalidateQueries({ queryKey: ['compat', pid] })
      } catch (e) {
        toast.push(errMsg(e), 'bad')
      }
    },
    [pid, qc, toast],
  )

  const ctx = useMemo<StepCtx | null>(() => {
    if (!project.data || !items.data || !roofTypes.data || !labor.data || !pricing.data) return null
    const p = project.data
    const layoutCount = p.layouts.reduce((s, l) => s + (l.summary?.count || 0), 0)
    const useLayout = sel.use_layout !== false && layoutCount > 0
    const limit = Number(sel.panel_limit || 0)
    const panelQty = useLayout ? (limit > 0 && limit < layoutCount ? limit : layoutCount) : sel.panel_qty || 0
    const panelId = sel.panel_item_id || p.layouts[0]?.panel_item_id
    const panel = items.data.find((i) => i.id === panelId)
    const wp = Number(panel?.specs?.wp || 0)
    return { project: p, sel, setSel, replaceSel, update, items: items.data, roofTypes: roofTypes.data, labor: labor.data, pricing: pricing.data.value, panelQty, kwp: Math.round(panelQty * wp) / 1000 }
  }, [project.data, items.data, roofTypes.data, labor.data, pricing.data, sel, setSel, replaceSel, update])

  if (project.isError) return <div className="text-bad">{errMsg(project.error)}</div>
  if (!ctx) return <Loading label={t('loading')} />
  const p = ctx.project
  const idx = STEPS.indexOf(step)
  const go = (s: Step) => nav(`/projects/${pid}/${s}`)

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link to="/" className="btn-quiet btn-sm -ml-2 px-2 text-ink-3">
          <ChevronLeft className="h-4 w-4" /> {t('projects_title')}
        </Link>
        <h1 className="min-w-0 flex-1 truncate">
          <span className="num text-ink-3">{p.number}</span> · {p.client_name || p.name}
        </h1>
        <div className="flex items-center gap-2 text-sm text-ink-2">
          {ctx.kwp > 0 && <Badge tone="sun">{fmtNum(ctx.kwp, 2)} kWp</Badge>}
          <Select value={p.status} onChange={(e) => update({ status: e.target.value })} className="input-sm w-auto" aria-label={t('status')}>
            {['draft', 'quoted', 'sent', 'accepted', 'ordered', 'installing', 'done', 'rejected'].map((s) => (
              <option key={s} value={s}>
                {t(`status_${s}` as Key)}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <nav className="-mx-4 mb-5 overflow-x-auto px-4 md:mx-0 md:px-0" aria-label="steps">
        <ol className="flex min-w-max gap-1 border-b border-line/10">
          {STEPS.map((s, i) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => go(s)}
                className={cx(
                  '-mb-px flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition',
                  s === step ? 'border-sun text-ink' : 'border-transparent text-ink-3 hover:text-ink',
                )}
                aria-current={s === step ? 'step' : undefined}
                data-testid={`tab-${s}`}
              >
                <span className={cx('num grid h-5 w-5 place-items-center rounded-full text-xs', s === step ? 'bg-ink text-white' : 'bg-surface-2 text-ink-3')}>{i + 1}</span>
                {t(`step_${s}` as Key)}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <section aria-label={t(`step_${step}` as Key)}>
        {step === 'client' && <ClientStep ctx={ctx} />}
        {step === 'params' && <ParamsStep ctx={ctx} />}
        {step === 'layout' && <LayoutStep ctx={ctx} />}
        {step === 'equipment' && <EquipmentStep ctx={ctx} />}
        {step === 'materials' && <MaterialsStep ctx={ctx} />}
        {step === 'labor' && <LaborStep ctx={ctx} />}
        {step === 'quote' && <QuoteStep ctx={ctx} />}
        {step === 'orders' && <OrdersStep ctx={ctx} />}
        {step === 'documents' && <DocumentsStep ctx={ctx} />}
      </section>

      <div className="mt-8 flex items-center justify-between">
        <button type="button" className="btn-ghost" disabled={idx === 0} onClick={() => go(STEPS[idx - 1])}>
          <ChevronLeft className="h-4 w-4" /> {t('back')}
        </button>
        <span className="text-xs text-ink-3" data-testid="text-autosave">
          {saveSel.isPending ? '…' : lang === 'bg' ? 'Промените се запазват и офертата се обновява автоматично' : 'Changes are saved and the quote updates automatically'}
        </span>
        {idx < STEPS.length - 1 ? (
          <button type="button" className="btn-primary" onClick={() => go(STEPS[idx + 1])} data-testid="button-next">
            {t('next')} <ChevronRight className="h-4 w-4" />
          </button>
        ) : (
          <span />
        )}
      </div>
    </div>
  )
}
