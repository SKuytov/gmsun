import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Database, Download, ExternalLink, FileText, Plus, RefreshCw, Search, Trash2, Upload } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Confirm, ErrorBox, Field, Input, Loading, Modal, NumInput, Select, Textarea, Toggle, cx, useToast } from '@/components/ui'
import { api, del, downloadFile, errMsg, get, patch, post, put } from '@/lib/api'
import { fmtMoney, fmtNum, useT, type Key } from '@/lib/i18n'
import { SITE_KINDS } from '@/lib/siteKind'
import type { CatalogItem, LaborOption, MountingRule, RoofType, Tier } from '@/lib/types'
import { useAuth } from '@/lib/auth'
import { DocLinks, useMountingSystems } from '@/components/MountingSystem'
import { DocsTab } from './CatalogDocs'

const TABS = ['items', 'labor', 'roofs', 'rules', 'docs'] as const
type Tab = (typeof TABS)[number]

interface CatalogPack {
  key: string
  label_bg: string
  label_en: string
  description_bg: string
  enabled: boolean
  items: number
  indicative: number
}

type PackResult = { added?: number; deleted?: number; rules?: number; quotes_updated?: number }

/** Optional reference databases next to the GM SUN final catalog (Aerocompact mounting, cables). */
function PacksBar({ admin }: { admin: boolean }) {
  const { lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const packs = useQuery({ queryKey: ['catalog', 'packs'], queryFn: () => get<CatalogPack[]>('/api/catalog/packs') })
  const [off, setOff] = useState<CatalogPack | null>(null)
  const toggle = useMutation({
    mutationFn: (p: CatalogPack) => (p.enabled ? del<PackResult>(`/api/catalog/packs/${p.key}`) : post<PackResult>(`/api/catalog/packs/${p.key}`)),
    onSuccess: (r: PackResult, p) => {
      qc.invalidateQueries()
      setOff(null)
      const name = lang === 'bg' ? p.label_bg : p.label_en
      toast.push(
        lang === 'bg'
          ? p.enabled ? `${name}: изтрити ${r.deleted ?? 0} артикула` : `${name}: добавени ${r.added ?? 0} артикула${r.rules ? ` и ${r.rules} правила` : ''}`
          : p.enabled ? `${name}: ${r.deleted ?? 0} items removed` : `${name}: ${r.added ?? 0} items added`,
        'ok',
      )
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  if (!packs.data?.length) return null
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="catalog-packs">
      <span className="text-ink-3">{lang === 'bg' ? 'Допълнителни бази:' : 'Extra databases:'}</span>
      {packs.data.map((p) => (
        <span key={p.key} className={cx('inline-flex items-center gap-2 rounded-md border px-2 py-1', p.enabled ? 'border-ok/40 bg-ok/5' : 'border-line')} title={p.description_bg} data-testid={`pack-${p.key}`}>
          <span className="font-medium text-ink">{lang === 'bg' ? p.label_bg : p.label_en}</span>
          <span className="text-ink-3">{p.enabled ? `${p.items} ${lang === 'bg' ? 'арт.' : 'items'}` : lang === 'bg' ? 'изключена' : 'off'}</span>
          {admin && (
            <button type="button" className="btn-ghost btn-sm !px-1.5 !py-0.5" disabled={toggle.isPending} onClick={() => (p.enabled ? setOff(p) : toggle.mutate(p))} data-testid={`button-pack-${p.key}`}>
              {p.enabled ? (lang === 'bg' ? 'Премахни' : 'Remove') : lang === 'bg' ? 'Добави' : 'Add'}
            </button>
          )}
        </span>
      ))}
      <Confirm
        open={!!off}
        onClose={() => setOff(null)}
        onConfirm={() => off && toggle.mutate(off)}
        title={off ? (lang === 'bg' ? `Премахни „${off.label_bg}“` : `Remove ${off.label_en}`) : ''}
        text={
          lang === 'bg'
            ? 'Артикулите от тази база се изтриват (редовете в изпратени оферти и поръчки запазват текста си). Артикулите на GM SUN не се засягат. Базата може да се добави отново по всяко време.'
            : 'The items of this database are deleted (lines of sent quotes and orders keep their text). GM SUN items are not affected. It can be added again at any time.'
        }
        danger
      />
    </div>
  )
}

interface Meta {
  categories: string[]
  mounting_bases: string[]
}
interface SupplierStatus {
  supplier: string
  snapshot_items: number
  snapshot_file: string | null
  linked_items: number
  with_datasheet: number
  unverified_items: number
}
interface SyncResult {
  products?: number
  created?: number
  updated?: number
  datasheets?: number
  errors?: string[]
}
const SPEC_CATS = ['panel', 'inverter', 'battery']
const hasDatasheet = (i: CatalogItem) => !!(i.specs.datasheet_url || i.specs.datasheet_file)
const openDatasheet = (i: CatalogItem) => downloadFile(`/api/catalog/items/${i.id}/datasheet`, `${(i.sku || i.name).slice(0, 60)}.pdf`)

const CAT_LABELS: Record<string, [string, string]> = {
  panel: ['Фотоволтаични модули', 'PV modules'],
  inverter: ['Инвертори', 'Inverters'],
  battery: ['Батерии', 'Batteries'],
  battery_accessory: ['Аксесоари за батерии', 'Battery accessories'],
  switchboard: ['Ел. табла', 'Switchboards'],
  solar_cable: ['Соларен кабел', 'Solar cable'],
  power_cable: ['Силов кабел', 'Power cable'],
  mounting: ['Конструкция', 'Mounting'],
  electrical: ['Ел. материали', 'Electrical'],
  dc_protection: ['DC защита (предпазители, SPD, табла)', 'DC protection (fuses, SPD, boxes)'],
  ac_protection: ['AC защита (прекъсвачи, ДТЗ, SPD)', 'AC protection (MCB, RCD, SPD)'],
  grounding: ['Заземяване', 'Earthing'],
  cable_management: ['Укрепване на кабели', 'Cable management'],
  monitoring: ['Измерване и комуникация', 'Metering & communication'],
  accessory: ['Аксесоари', 'Accessories'],
  service: ['Услуги', 'Services'],
  transport: ['Транспорт', 'Transport'],
  other: ['Други', 'Other'],
}
const BASIS_LABELS: Record<string, [string, string]> = {
  per_module: ['на модул', 'per module'],
  per_line: ['на ред модули', 'per row of modules'],
  per_rail: ['на шина (бр.)', 'per rail piece'],
  per_rail_meter: ['на метър шина', 'per rail metre'],
  per_fixation: ['на фиксатор / кука', 'per fixation / hook'],
  per_mid_clamp: ['на средна скоба', 'per mid clamp'],
  per_end_clamp: ['на крайна скоба', 'per end clamp'],
  per_connector: ['на съединител', 'per rail connector'],
  per_clamp: ['на скоба/опорна точка', 'per clamp / support point'],
  per_string: ['на стринг', 'per string'],
  per_kwp: ['на kWp', 'per kWp'],
  per_project: ['фиксирано за проект', 'fixed per project'],
}
const label = (map: Record<string, [string, string]>, code: string, lang: string) => (map[code] ? map[code][lang === 'bg' ? 0 : 1] : code)

export default function CatalogPage() {
  const { t, lang } = useT()
  const { tab: tabParam } = useParams()
  const nav = useNavigate()
  const tab: Tab = (TABS as readonly string[]).includes(tabParam || '') ? (tabParam as Tab) : 'items'
  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1>{t('catalog_title')}</h1>
        <div className="inline-flex gap-1 rounded-md bg-surface-2 p-1">
          {TABS.map((x) => (
            <button key={x} type="button" onClick={() => nav(`/catalog/${x}`)} className={cx('h-9 rounded px-3 text-sm font-medium', tab === x ? 'bg-surface shadow-card' : 'text-ink-2')} data-testid={`tab-catalog-${x}`}>
              {{ items: t('nav_catalog'), labor: t('labor'), roofs: t('roof_types_title'), rules: t('mounting_rules_title'), docs: t('local_docs') }[x]}
            </button>
          ))}
        </div>
      </div>
      {tab === 'items' && <ItemsTab lang={lang} />}
      {tab === 'labor' && <LaborTab />}
      {tab === 'roofs' && <RoofsTab lang={lang} />}
      {tab === 'rules' && <RulesTab lang={lang} />}
      {tab === 'docs' && <DocsTab lang={lang} />}
    </div>
  )
}

// ----------------------------------------------------------------- items
export function TierBadge({ tier, manual }: { tier?: Tier | null; manual?: boolean }) {
  const { t } = useT()
  if (!tier) return <span className="text-ink-3">—</span>
  const tone = tier === 'premium' ? 'bg-sun-soft text-sun-ink' : tier === 'economy' ? 'bg-ok/15 text-ok' : 'bg-line/20 text-ink-2'
  return (
    <span className={cx('inline-flex items-center whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium', tone)} title={manual ? undefined : t('tier_auto')}>
      {t(`tier_${tier}` as Key)}
      {!manual && <span className="ml-0.5 opacity-60">·</span>}
    </span>
  )
}

function ItemsTab({ lang }: { lang: string }) {
  const { t } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const admin = user?.role === 'admin'
  const [cat, setCat] = useState('')
  const [q, setQ] = useState('')
  const [inactive, setInactive] = useState(false)
  const [editing, setEditing] = useState<Partial<CatalogItem> | null>(null)
  const [toDelete, setToDelete] = useState<CatalogItem | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [datasetOpen, setDatasetOpen] = useState(false)
  const [syncOpen, setSyncOpen] = useState(false)
  const [reseedOpen, setReseedOpen] = useState(false)
  const final = useQuery({ queryKey: ['catalog', 'final-status'], queryFn: () => get<FinalStatus>('/api/catalog/final/status') })
  const curated = !!final.data?.curated
  const status = useQuery({ queryKey: ['catalog', 'supplier-status'], queryFn: () => get<SupplierStatus>('/api/catalog/supplier/status'), enabled: admin && final.isSuccess && !curated })
  const [reapplyOpen, setReapplyOpen] = useState(false)
  const reapply = useMutation({
    mutationFn: () => post<{ kept?: number; deleted?: number; quotes_updated?: number }>('/api/catalog/final/reapply'),
    onSuccess: (r) => {
      qc.invalidateQueries()
      setReapplyOpen(false)
      toast.push(lang === 'bg' ? `Финалният каталог е възстановен${r.deleted != null ? ` · изтрити ${r.deleted}` : ''}${r.quotes_updated != null ? ` · обновени оферти ${r.quotes_updated}` : ''}` : 'Final catalog restored', 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const reseed = useMutation({
    mutationFn: () => post<{ added_items: number }>('/api/catalog/mounting/reseed'),
    onSuccess: (r) => {
      qc.invalidateQueries()
      setReseedOpen(false)
      toast.push(`${r.added_items} ${t('added_items')}`, 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const items = useQuery({ queryKey: ['catalog', 'items', inactive], queryFn: () => get<CatalogItem[]>(`/api/catalog/items${inactive ? '?include_inactive=true' : ''}`) })
  const meta = useQuery({ queryKey: ['catalog', 'meta'], queryFn: () => get<Meta>('/api/catalog/meta') })
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['catalog'] })
    qc.invalidateQueries({ queryKey: ['quotes'] })
    qc.invalidateQueries({ queryKey: ['compat'] })
  }

  const save = useMutation({
    mutationFn: (it: Partial<CatalogItem>) => (it.id ? patch<CatalogItem>(`/api/catalog/items/${it.id}`, it) : post<CatalogItem>('/api/catalog/items', it)),
    onSuccess: () => {
      invalidate()
      setEditing(null)
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({ mutationFn: (id: number) => del(`/api/catalog/items/${id}`), onSuccess: invalidate, onError: (e) => toast.push(errMsg(e), 'bad') })
  const dup = useMutation({ mutationFn: (id: number) => post(`/api/catalog/items/${id}/duplicate`), onSuccess: invalidate, onError: (e) => toast.push(errMsg(e), 'bad') })

  const list = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (items.data || []).filter((i) => (!cat || i.category === cat) && (!s || [i.name, i.sku || '', i.manufacturer || ''].some((v) => v.toLowerCase().includes(s))))
  }, [items.data, cat, q])
  const catLabel = (code: string) => label(CAT_LABELS, code, lang)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={cat} onChange={(e) => setCat(e.target.value)} className="w-auto" aria-label={t('category')} data-testid="select-category">
          <option value="">{t('all')}</option>
          {(meta.data?.categories || []).map((c) => (
            <option key={c} value={c}>
              {catLabel(c)}
            </option>
          ))}
        </Select>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <Input placeholder={t('search')} value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" />
        </div>
        <Toggle checked={inactive} onChange={setInactive} label={t('show_inactive')} />
        {admin && (
          <div className="ml-auto flex flex-wrap gap-1">
            {curated ? (
              <button type="button" className="btn-ghost btn-sm" onClick={() => setReapplyOpen(true)} data-testid="button-final-reapply" title={lang === 'bg' ? 'Връща 56-те артикула на GM SUN с цените и данните от финалния набор' : 'Restores the 56 GM SUN items with the prices and data of the final set'}>
                <RefreshCw className="h-4 w-4" /> {lang === 'bg' ? 'Възстанови финалния каталог' : 'Restore final catalog'}
              </button>
            ) : (
              final.isSuccess && (
                <>
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setSyncOpen(true)} data-testid="button-supplier-sync" title={t('supplier_sync_hint')}>
                    <RefreshCw className="h-4 w-4" /> {t('supplier_sync')}
                  </button>
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setReseedOpen(true)} data-testid="button-aero-reseed" title={t('aero_reseed_hint')}>
                    <RefreshCw className="h-4 w-4" /> {t('aero_reseed')}
                  </button>
                </>
              )
            )}
            <button type="button" className="btn-ghost btn-sm" onClick={() => setImportOpen(true)} data-testid="button-import">
              <Upload className="h-4 w-4" /> {t('import_xlsx')}
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => downloadFile('/api/catalog/export', 'gmsun-catalog.xlsx').catch((e) => toast.push(errMsg(e), 'bad'))}>
              <Download className="h-4 w-4" /> {t('export_xlsx')}
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setDatasetOpen(true)} data-testid="button-dataset" title={t('dataset_hint')}>
              <Database className="h-4 w-4" /> {t('dataset_all_tables')}
            </button>
            <button type="button" className="btn-accent btn-sm" onClick={() => setEditing({ category: cat || 'panel', unit: 'бр.', purchase_price: 0, active: true, specs: {} })} data-testid="button-new-item">
              <Plus className="h-4 w-4" /> {t('new_item')}
            </button>
          </div>
        )}
      </div>
      {curated && final.data && (
        <p className="text-xs text-ink-3" data-testid="text-final-status">
          {lang === 'bg'
            ? `Финален каталог на GM SUN: ${final.data.final_present} от ${final.data.final_items} артикула · общо в каталога ${final.data.items_total}. Панели, инвертори и батерии се предлагат само от тези артикули.`
            : `GM SUN final catalog: ${final.data.final_present} of ${final.data.final_items} items · ${final.data.items_total} in the catalog. Panels, inverters and batteries are suggested only from these items.`}
          {final.data.missing.length > 0 && <span className="text-warn"> {lang === 'bg' ? `Липсват: ${final.data.missing.join(', ')}` : `Missing: ${final.data.missing.join(', ')}`}</span>}
        </p>
      )}
      {curated && <PacksBar admin={admin} />}
      {admin && !curated && status.data && (
        <p className="text-xs text-ink-3" data-testid="text-supplier-status">
          {t('supplier_status')} {status.data.supplier}: {status.data.linked_items} {t('supplier_linked')} · {status.data.with_datasheet} {t('supplier_with_ds')} · {status.data.unverified_items} {t('supplier_unverified')}
          {status.data.snapshot_file ? ` · ${status.data.snapshot_file} (${status.data.snapshot_items})` : ''}
        </p>
      )}
      {items.isLoading && <Loading label={t('loading')} />}
      {items.data && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="tbl min-w-[800px]">
              <thead>
                <tr>
                  <th>{t('category')}</th>
                  <th>{t('name')}</th>
                  <th>{t('manufacturer')}</th>
                  <th>{t('supplier')}</th>
                  <th className="text-right">{t('lead_time_days')}</th>
                  <th>{t('tier')}</th>
                  <th>{t('unit')}</th>
                  <th className="text-right">{t('purchase_price')}</th>
                  <th className="text-right">{t('markup')}</th>
                  <th className="text-right">{t('sell_price')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((i) => (
                  <tr key={i.id} className={cx(!i.active && 'opacity-50')} data-testid={`row-item-${i.id}`}>
                    <td>
                      <Badge>{catLabel(i.category)}</Badge>
                    </td>
                    <td>
                      <button type="button" className="text-left font-medium hover:underline" onClick={() => admin && setEditing(i)}>
                        {i.name}
                      </button>
                      {i.sku && <span className="ml-2 text-xs text-ink-3">{i.sku}</span>}
                      {SPEC_CATS.includes(i.category) && i.specs.specs_verified === false && !!i.specs.spec_source && (
                        <span className="ml-2 whitespace-nowrap rounded bg-warn/15 px-1.5 py-0.5 text-[11px] text-warn" title={t('specs_unverified_hint')}>
                          {t('specs_unverified')}
                        </span>
                      )}
                      <span className="ml-1 inline-flex gap-0.5 align-middle">
                        {hasDatasheet(i) && (
                          <button type="button" className="btn-quiet btn-sm" onClick={() => openDatasheet(i).catch((e) => toast.push(errMsg(e), 'bad'))} aria-label={t('datasheet')} title={t('datasheet')} data-testid={`button-datasheet-${i.id}`}>
                            <FileText className="h-4 w-4" />
                          </button>
                        )}
                        {typeof i.specs.product_url === 'string' && (
                          <a href={i.specs.product_url} target="_blank" rel="noreferrer" className="btn-quiet btn-sm" aria-label={t('product_page')} title={t('product_page')}>
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        )}
                      </span>
                    </td>
                    <td className="text-ink-2">{i.manufacturer}</td>
                    <td className="text-ink-2">{i.supplier || <span className="text-ink-3">—</span>}</td>
                    <td className={cx('num text-right', i.lead_time_days == null && 'text-ink-3')} title={i.lead_time_days == null ? t('lead_time_hint') : undefined}>
                      {i.effective_lead_time_days ?? '—'}
                    </td>
                    <td>
                      <TierBadge tier={i.effective_tier} manual={!!i.tier} />
                    </td>
                    <td className="text-ink-2">{i.unit}</td>
                    <td className="num text-right">{i.purchase_price ? fmtNum(i.purchase_price) : <span className="text-warn">0</span>}</td>
                    <td className="num text-right text-ink-3">{i.markup_pct ?? '·'}</td>
                    <td className="num text-right font-medium">{fmtNum(i.effective_price)}</td>
                    <td className="whitespace-nowrap text-right">
                      {admin && (
                        <>
                          <button type="button" className="btn-quiet btn-sm" onClick={() => dup.mutate(i.id)} aria-label={t('duplicate')} title={t('duplicate')}>
                            <Copy className="h-4 w-4" />
                          </button>
                          <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => setToDelete(i)} aria-label={t('delete')} title={t('delete')}>
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-line/10 px-3 py-2 text-xs text-ink-3">
            {list.length} / {items.data.length}
          </div>
        </div>
      )}

      {editing && <ItemModal item={editing} meta={meta.data} onClose={() => setEditing(null)} onSave={(it) => save.mutate(it)} busy={save.isPending} />}
      <ImportModal open={importOpen} onClose={() => setImportOpen(false)} categories={meta.data?.categories || []} lang={lang} onDone={invalidate} />
      <DatasetModal open={datasetOpen} onClose={() => setDatasetOpen(false)} onDone={() => qc.invalidateQueries()} />
      <SyncModal open={syncOpen} onClose={() => setSyncOpen(false)} onDone={() => qc.invalidateQueries()} />
      <Confirm
        open={reapplyOpen}
        onClose={() => setReapplyOpen(false)}
        onConfirm={() => reapply.mutate()}
        title={lang === 'bg' ? 'Възстанови финалния каталог' : 'Restore final catalog'}
        text={
          lang === 'bg'
            ? 'Цените и данните на 56-те артикула, цените на конструкциите по тип покрив и таблицата труд се връщат към финалния набор, а всички други артикули (вкл. ръчно добавени) се изтриват. Настройките (фирма, ценообразуване, ставка труд) не се променят. Преди това се прави резервно копие. Черновите оферти се преизчисляват автоматично; изпратените остават непроменени.'
            : 'Prices and data of the 56 items, roof construction prices and the labor matrix are reset to the final set and every other item (including manually added ones) is deleted. Settings (company, pricing, labor rate) are kept. A backup is made first. Draft quotes are recalculated automatically; sent quotes stay unchanged.'
        }
        danger
      />
      <Confirm open={reseedOpen} onClose={() => setReseedOpen(false)} onConfirm={() => reseed.mutate()} title={t('aero_reseed')} text={t('aero_reseed_hint')} />
      <Confirm open={!!toDelete} onClose={() => setToDelete(null)} onConfirm={() => toDelete && remove.mutate(toDelete.id)} title={t('delete')} text={`${t('confirm_delete')} ${toDelete?.name}`} danger />
    </div>
  )
}

function ItemModal({ item, meta, onClose, onSave, busy }: { item: Partial<CatalogItem>; meta?: Meta; onClose: () => void; onSave: (it: Partial<CatalogItem>) => void; busy: boolean }) {
  const { t, lang } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState<Partial<CatalogItem>>({ ...item })
  const suppliersQ = useQuery({ queryKey: ['settings', 'suppliers'], queryFn: () => get<{ value: { list?: { name: string }[] } }>('/api/settings/suppliers') })
  const supplierNames = (suppliersQ.data?.value.list || []).map((x) => x.name)
  const [specs, setSpecs] = useState(JSON.stringify(item.specs || {}, null, 2))
  const [specsErr, setSpecsErr] = useState('')
  const [autofill, setAutofill] = useState(true)
  const fileRef = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api<CatalogItem>(`/api/catalog/items/${f.id}/datasheet?autofill=${autofill}`, { method: 'POST', form })
    },
    onSuccess: (it) => {
      setF((cur) => ({ ...cur, specs: it.specs }))
      setSpecs(JSON.stringify(it.specs || {}, null, 2))
      qc.invalidateQueries({ queryKey: ['catalog'] })
      qc.invalidateQueries({ queryKey: ['quotes'] })
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const curSpecs = (() => {
    try {
      return JSON.parse(specs || '{}') as Record<string, unknown>
    } catch {
      return {}
    }
  })()
  const submit = () => {
    try {
      const sp = JSON.parse(specs || '{}')
      onSave({ ...f, specs: sp })
    } catch {
      setSpecsErr('JSON')
    }
  }
  const spec = (k: string, label: string, hint?: string) => (
    <Field label={label} hint={hint}>
      <NumInput
        value={(() => {
          try {
            return JSON.parse(specs || '{}')[k] ?? null
          } catch {
            return null
          }
        })()}
        onChange={(v) => {
          try {
            const o = JSON.parse(specs || '{}')
            o[k] = v
            setSpecs(JSON.stringify(o, null, 2))
          } catch {
            /* ignore */
          }
        }}
      />
    </Field>
  )
  const commonSpecs: Record<string, React.ReactNode> = {
    panel: (
      <>
        {spec('wp', 'Wp')}
        {spec('width_mm', 'Width mm')}
        {spec('height_mm', 'Height mm')}
        {spec('voc', 'Voc')}
        {spec('isc', 'Isc')}
        {spec('vmp', 'Vmp')}
      </>
    ),
    inverter: (
      <>
        {spec('ac_power_kw', 'AC kW')}
        {spec('max_pv_kw', 'Max PV kWp')}
        {spec('phases', 'Phases 1/3')}
        {spec('mppt_count', 'MPPT')}
        {spec('max_dc_voltage', 'Max DC V')}
        {spec('mppt_min_v', 'MPPT min V')}
        {spec('mppt_max_v', 'MPPT max V')}
        {spec('battery_v_min', 'Batt V min')}
        {spec('battery_v_max', 'Batt V max')}
      </>
    ),
    battery: (
      <>
        {spec('kwh', 'kWh')}
        {spec('nominal_v', 'Nominal V')}
        {spec('max_parallel', 'Max parallel')}
      </>
    ),
    switchboard: <>{spec('phases', 'Phases 1/3')}</>,
    power_cable: <>{spec('cores', 'Cores')}{spec('section_mm2', 'mm²')}</>,
  }
  return (
    <Modal
      open
      onClose={onClose}
      title={f.id ? t('edit') : t('new_item')}
      wide
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t('cancel')}
          </button>
          <button type="button" className="btn-primary" onClick={submit} disabled={busy || !f.name} data-testid="button-save-item">
            {t('save')}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label={t('category')}>
          <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            {(meta?.categories || []).map((c) => (
              <option key={c} value={c}>
                {label(CAT_LABELS, c, lang)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t('name')} className="sm:col-span-2">
          <Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="input-item-name" />
        </Field>
        <Field label={t('manufacturer')}>
          <Input value={f.manufacturer || ''} onChange={(e) => setF({ ...f, manufacturer: e.target.value })} />
        </Field>
        <Field label={t('sku')}>
          <Input value={f.sku || ''} onChange={(e) => setF({ ...f, sku: e.target.value })} />
        </Field>
        <Field label={t('unit')}>
          <Input value={f.unit || ''} onChange={(e) => setF({ ...f, unit: e.target.value })} />
        </Field>
        <Field label={`${t('purchase_price')} (EUR)`}>
          <NumInput value={f.purchase_price ?? 0} min={0} onChange={(v) => setF({ ...f, purchase_price: v })} data-testid="input-item-price" />
        </Field>
        <Field label={t('markup')} hint={lang === 'bg' ? 'празно = по подразбиране' : 'empty = default'}>
          <NumInput value={f.markup_pct ?? null} min={0} onChange={(v) => setF({ ...f, markup_pct: v })} />
        </Field>
        <Field label={`${t('sell_price')} (EUR)`} hint={lang === 'bg' ? 'празно = доставна + надценка' : 'empty = purchase + markup'}>
          <NumInput value={f.sell_price ?? null} min={0} onChange={(v) => setF({ ...f, sell_price: v })} />
        </Field>
        <Field label={t('warranty')}>
          <Input value={f.warranty || ''} onChange={(e) => setF({ ...f, warranty: e.target.value })} />
        </Field>
        <Field label={t('supplier')}>
          <Input list="gmsun-suppliers" value={f.supplier || ''} onChange={(e) => setF({ ...f, supplier: e.target.value || null })} data-testid="input-item-supplier" />
          <datalist id="gmsun-suppliers">
            {supplierNames.map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
        </Field>
        <Field label={t('supplier_sku')}>
          <Input value={f.supplier_sku || ''} onChange={(e) => setF({ ...f, supplier_sku: e.target.value || null })} />
        </Field>
        <Field label={t('lead_time_days')} hint={t('lead_time_hint')}>
          <NumInput value={f.lead_time_days ?? null} min={0} onChange={(v) => setF({ ...f, lead_time_days: v == null ? null : Math.round(v) })} data-testid="input-item-lead" />
        </Field>
        <Field label={t('tier')} hint={f.tier ? undefined : `${t('tier_auto')}${f.effective_tier ? `: ${t(`tier_${f.effective_tier}` as Key)}` : ''}`}>
          <Select value={f.tier || ''} onChange={(e) => setF({ ...f, tier: (e.target.value || null) as Tier | null })}>
            <option value="">{t('tier_auto')}</option>
            <option value="economy">{t('tier_economy')}</option>
            <option value="standard">{t('tier_standard')}</option>
            <option value="premium">{t('tier_premium')}</option>
          </Select>
        </Field>
        <Field label={t('active')} className="self-end">
          <Toggle checked={f.active !== false} onChange={(v) => setF({ ...f, active: v })} />
        </Field>
        <Field label={t('notes')} className="sm:col-span-3">
          <Input value={f.description || ''} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        {f.category && commonSpecs[f.category] && <div className="grid grid-cols-2 gap-3 sm:col-span-3 sm:grid-cols-4">{commonSpecs[f.category]}</div>}
        <div className="flex flex-wrap items-center gap-2 sm:col-span-3">
          {f.id && (curSpecs.datasheet_url || curSpecs.datasheet_file) ? (
            <button type="button" className="btn-ghost btn-sm" onClick={() => openDatasheet(f as CatalogItem).catch((e) => toast.push(errMsg(e), 'bad'))}>
              <FileText className="h-4 w-4" /> {t('datasheet')}
            </button>
          ) : null}
          {typeof curSpecs.product_url === 'string' && (
            <a href={curSpecs.product_url} target="_blank" rel="noreferrer" className="btn-ghost btn-sm">
              <ExternalLink className="h-4 w-4" /> {t('product_page')}
            </a>
          )}
          {f.id && (
            <>
              <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} data-testid="input-datasheet-file" />
              <button type="button" className="btn-ghost btn-sm" onClick={() => fileRef.current?.click()} disabled={upload.isPending} data-testid="button-upload-datasheet">
                <Upload className="h-4 w-4" /> {upload.isPending ? t('loading') : t('upload_datasheet')}
              </button>
              {SPEC_CATS.includes(f.category || '') && <Toggle checked={autofill} onChange={setAutofill} label={t('autofill_specs')} />}
            </>
          )}
          {SPEC_CATS.includes(f.category || '') && curSpecs.specs_verified === false && !!curSpecs.spec_source && (
            <span className="text-xs text-warn" title={t('specs_unverified_hint')}>
              {t('specs_unverified')} ({String(curSpecs.spec_source)})
            </span>
          )}
        </div>
        <Field label={t('specs')} className="sm:col-span-3" error={specsErr}>
          <Textarea className="font-mono text-xs" rows={6} value={specs} onChange={(e) => setSpecs(e.target.value)} />
        </Field>
      </div>
    </Modal>
  )
}

function ImportModal({ open, onClose, categories, lang, onDone }: { open: boolean; onClose: () => void; categories: Meta['categories']; lang: string; onDone: () => void }) {
  const { t } = useT()
  const [cat, setCat] = useState('inverter')
  const [res, setRes] = useState<{ created: number; updated: number; skipped: number } | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLInputElement>(null)
  const run = async (file: File) => {
    setBusy(true)
    setErr('')
    try {
      const fd = new FormData()
      fd.append('file', file)
      setRes(await api(`/api/catalog/import?category=${cat}`, { form: fd }))
      onDone()
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={t('import_xlsx')}>
      <div className="flex flex-col gap-3">
        <p className="text-sm text-ink-2">{t('import_hint')}</p>
        <Field label={`${t('category')} (${lang === 'bg' ? 'по подразбиране, ако файлът няма секции' : 'default if the file has no sections'})`}>
          <Select value={cat} onChange={(e) => setCat(e.target.value)}>
            {categories.map((c) => (
              <option key={c} value={c}>
                {label(CAT_LABELS, c, lang)}
              </option>
            ))}
          </Select>
        </Field>
        <input ref={ref} type="file" accept=".xlsx" className="hidden" onChange={(e) => e.target.files?.[0] && run(e.target.files[0])} />
        <button type="button" className="btn-primary" onClick={() => ref.current?.click()} disabled={busy}>
          <Upload className="h-4 w-4" /> {busy ? '…' : '.xlsx'}
        </button>
        {res && (
          <p className="text-sm">
            {lang === 'bg' ? 'Създадени' : 'Created'}: <b>{res.created}</b> · {lang === 'bg' ? 'Обновени' : 'Updated'}: <b>{res.updated}</b> · {lang === 'bg' ? 'Пропуснати' : 'Skipped'}: <b>{res.skipped}</b>
          </p>
        )}
        {err && <ErrorBox>{err}</ErrorBox>}
      </div>
    </Modal>
  )
}

type DatasetReport = {
  files: string[]
  tables: Record<string, { title: string; rows: number; created: number; updated: number; skipped: number; errors: string[] }>
  ignored_sheets: string[]
  created: number
  updated: number
  skipped: number
  errors: number
  deleted?: number
  quotes_updated?: number
}

type FinalStatus = { curated: boolean; done: boolean; final_items: number; final_present: number; items_total: number; missing: string[]; migration: { at?: string; backup?: string; deleted?: number } }

/** Whole-dataset round trip: every editable table as Excel (one workbook or a .zip of workbooks) and back. */
function DatasetModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t, lang } = useT()
  const toast = useToast()
  const [res, setRes] = useState<DatasetReport | null>(null)
  const [replace, setReplace] = useState(false)
  const [fill, setFill] = useState<Record<string, number> | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLInputElement>(null)
  const dl = (path: string, name: string) => downloadFile(path, name).catch((e) => toast.push(errMsg(e), 'bad'))
  const run = async (file: File) => {
    setBusy(true)
    setErr('')
    setRes(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      setRes(await api<DatasetReport>(`/api/catalog/dataset/import${replace ? '?replace_items=true' : ''}`, { form: fd }))
      onDone()
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
      if (ref.current) ref.current.value = ''
    }
  }
  const runFill = async () => {
    setBusy(true)
    setErr('')
    try {
      const r = await post<Record<string, number> & { unpriced_left: string[] }>('/api/catalog/dataset/fill-missing')
      const { unpriced_left: _u, ...rest } = r
      setFill(rest)
      onDone()
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={t('dataset_all_tables')}>
      <div className="flex flex-col gap-4">
        <section className="flex flex-col gap-2">
          <h4 className="text-sm font-semibold">{t('dataset_export')}</h4>
          <p className="text-sm text-ink-2">{t('dataset_export_hint')}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary btn-sm" onClick={() => dl('/api/catalog/dataset.xlsx', 'gmsun-dataset.xlsx')} data-testid="button-dataset-xlsx">
              <Download className="h-4 w-4" /> {t('dataset_one_xlsx')}
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => dl('/api/catalog/dataset.zip', 'gmsun-dataset.zip')} data-testid="button-dataset-zip">
              <Download className="h-4 w-4" /> {t('dataset_zip')}
            </button>
          </div>
        </section>
        <section className="flex flex-col gap-2">
          <h4 className="text-sm font-semibold">{t('dataset_import')}</h4>
          <p className="text-sm text-ink-2">{t('dataset_import_hint')}</p>
          <input ref={ref} type="file" accept=".xlsx,.zip" className="hidden" onChange={(e) => e.target.files?.[0] && run(e.target.files[0])} data-testid="input-dataset-file" />
          <label className="flex items-start gap-2 rounded-md border border-line/15 p-2 text-sm">
            <input type="checkbox" className="mt-1" checked={replace} onChange={(e) => setReplace(e.target.checked)} data-testid="checkbox-dataset-replace" />
            <span>
              <span className="font-medium">{lang === 'bg' ? 'Замени каталога (изтрий артикулите, които липсват във файла)' : 'Replace the catalog (delete items missing from the file)'}</span>
              <span className="block text-xs text-ink-3">
                {lang === 'bg'
                  ? 'Файлът става единственият списък с артикули. Преди това се прави резервно копие; импортът се отказва изцяло, ако листът „Артикули“ липсва или има грешки. Офертите остават, но редовете им губят връзката с изтритите артикули.'
                  : 'The file becomes the only item list. A backup is made first; the import is refused entirely if the "Артикули" sheet is missing or has errors. Quotes are kept, their lines lose the link to deleted items.'}
              </span>
            </span>
          </label>
          <div>
            <button type="button" className="btn-accent btn-sm" onClick={() => ref.current?.click()} disabled={busy} data-testid="button-dataset-import">
              <Upload className="h-4 w-4" /> {busy ? '…' : t('dataset_choose_file')}
            </button>
          </div>
          {res && (
            <div className="rounded-md border border-line bg-surface-2 p-3 text-sm" data-testid="text-dataset-result">
              <p>
                {lang === 'bg' ? 'Файлове' : 'Files'}: {res.files.length} · {lang === 'bg' ? 'Създадени' : 'Created'}: <b>{res.created}</b> · {lang === 'bg' ? 'Обновени' : 'Updated'}: <b>{res.updated}</b> ·{' '}
                {lang === 'bg' ? 'Без промяна' : 'Unchanged'}: <b>{res.skipped}</b> · {lang === 'bg' ? 'Грешки' : 'Errors'}: <b className={res.errors ? 'text-bad' : ''}>{res.errors}</b>
                {res.deleted != null && (
                  <>
                    {' '}· {lang === 'bg' ? 'Изтрити' : 'Deleted'}: <b>{res.deleted}</b>
                  </>
                )}
                {res.quotes_updated != null && (
                  <>
                    {' '}· {lang === 'bg' ? 'Обновени чернови оферти' : 'Draft quotes updated'}: <b>{res.quotes_updated}</b>
                  </>
                )}
              </p>
              <ul className="mt-2 flex flex-col gap-1">
                {Object.values(res.tables).map((tb) => (
                  <li key={tb.title}>
                    <span className="font-medium">{tb.title}</span>: {tb.rows} {lang === 'bg' ? 'реда' : 'rows'} · +{tb.created} / ✎{tb.updated}
                    {tb.errors.length > 0 && (
                      <ul className="ml-4 mt-1 list-disc text-xs text-bad">
                        {tb.errors.slice(0, 15).map((e, i) => (
                          <li key={i}>{e}</li>
                        ))}
                        {tb.errors.length > 15 && <li>… +{tb.errors.length - 15}</li>}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
              {res.ignored_sheets.length > 0 && (
                <p className="mt-2 text-xs text-ink-3">
                  {lang === 'bg' ? 'Пропуснати листове' : 'Ignored sheets'}: {res.ignored_sheets.join(', ')}
                </p>
              )}
            </div>
          )}
        </section>
        <section className="flex flex-col gap-2 border-t border-line pt-3">
          <h4 className="text-sm font-semibold">{t('dataset_fill')}</h4>
          <p className="text-sm text-ink-2">{t('dataset_fill_hint')}</p>
          <div>
            <button type="button" className="btn-ghost btn-sm" onClick={runFill} disabled={busy} data-testid="button-dataset-fill">
              <RefreshCw className="h-4 w-4" /> {t('dataset_fill')}
            </button>
          </div>
          {fill && (
            <p className="text-xs text-ink-2">
              {lang === 'bg' ? 'Попълнени' : 'Filled'}: {lang === 'bg' ? 'цени' : 'prices'} {fill.price} · {lang === 'bg' ? 'срокове' : 'lead times'} {fill.lead_time} · {lang === 'bg' ? 'класове' : 'tiers'} {fill.tier} ·{' '}
              {lang === 'bg' ? 'доставчици' : 'suppliers'} {fill.supplier} · SKU {fill.sku}
            </p>
          )}
        </section>
        {err && <ErrorBox>{err}</ErrorBox>}
      </div>
    </Modal>
  )
}

// ----------------------------------------------------------------- labor
function SyncModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t, lang } = useT()
  const toast = useToast()
  const [withDs, setWithDs] = useState(false)
  const [overwrite, setOverwrite] = useState(false)
  const [result, setResult] = useState<SyncResult | null>(null)
  const sync = useMutation({
    mutationFn: () => post<SyncResult>(`/api/catalog/sync/green-energy?parse_datasheets=${withDs}&overwrite_specs=${overwrite}`),
    onSuccess: (r) => {
      setResult(r)
      onDone()
      toast.push(t('supplier_sync_done'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('supplier_sync')}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {t('close')}
          </button>
          <button type="button" className="btn-primary" onClick={() => sync.mutate()} disabled={sync.isPending} data-testid="button-run-sync">
            {sync.isPending ? t('loading') : t('supplier_sync')}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm text-ink-2">{t('supplier_sync_hint')}</p>
        <Toggle checked={withDs} onChange={setWithDs} label={t('supplier_sync_with_ds')} />
        <Toggle checked={overwrite} onChange={setOverwrite} label={t('supplier_sync_overwrite')} />
        {sync.isPending && <Loading label={lang === 'bg' ? 'Изтегляне от green-energy.bg…' : 'Downloading from green-energy.bg…'} />}
        {result && (
          <div className="rounded bg-ok/10 p-2 text-sm" data-testid="text-sync-result">
            {lang === 'bg' ? 'Продукти' : 'Products'}: {result.products ?? '—'} · {lang === 'bg' ? 'нови' : 'new'}: {result.created ?? 0} · {lang === 'bg' ? 'обновени' : 'updated'}: {result.updated ?? 0}
            {result.datasheets != null ? ` · datasheets: ${result.datasheets}` : ''}
            {result.errors && result.errors.length > 0 && <div className="mt-1 text-xs text-warn">{result.errors.slice(0, 5).join('; ')}</div>}
          </div>
        )}
      </div>
    </Modal>
  )
}

function LaborTab() {
  const { t, lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const labor = useQuery({ queryKey: ['labor', 'all'], queryFn: () => get<LaborOption[]>('/api/catalog/labor?include_inactive=true') })
  const inv = () => {
    qc.invalidateQueries({ queryKey: ['labor'] })
    qc.invalidateQueries({ queryKey: ['quotes'] })
  }
  const save = useMutation({
    mutationFn: (o: Partial<LaborOption>) => (o.id ? put(`/api/catalog/labor/${o.id}`, o) : post('/api/catalog/labor', o)),
    onSuccess: inv,
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({ mutationFn: (id: number) => del(`/api/catalog/labor/${id}`), onSuccess: inv, onError: (e) => toast.push(errMsg(e), 'bad') })
  const [nw, setNw] = useState({ days: 1, workers: 2, price: 1000 })
  const rows = labor.data || []
  const days = Array.from(new Set(rows.map((r) => r.days))).sort((a, b) => a - b)
  const workers = Array.from(new Set(rows.map((r) => r.workers))).sort((a, b) => a - b)
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-2">{lang === 'bg' ? 'Цена за труд според брой дни и брой работници. Променете стойност директно в клетката.' : 'Labor price by number of days and workers. Edit a value directly in its cell.'}</p>
      {labor.isLoading && <Loading />}
      <div className="card overflow-x-auto p-2">
        <table className="tbl !w-auto">
          <thead>
            <tr>
              <th>
                {t('days')} \ {t('workers')}
              </th>
              {workers.map((w) => (
                <th key={w} className="w-40 !text-center">
                  {w}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d}>
                <td className="num font-medium">{d}</td>
                {workers.map((w) => {
                  const o = rows.find((r) => r.days === d && r.workers === w)
                  return (
                    <td key={w} className="p-0.5">
                      {o ? (
                        <div className="flex items-center gap-1">
                          <NumInput className="cell-input min-w-[5rem]" value={o.price} min={0} onChange={(v) => v !== o.price && save.mutate({ ...o, price: v })} />
                          <button type="button" className="btn-quiet btn-sm h-7 w-7 px-0 text-bad" onClick={() => remove.mutate(o.id)} aria-label={t('delete')}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <button type="button" className="btn-quiet btn-sm w-full text-ink-3" onClick={() => save.mutate({ days: d, workers: w, price: 0, active: true })}>
                          +
                        </button>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card flex flex-wrap items-end gap-3 p-3">
        <Field label={t('days')}>
          <NumInput className="w-24" value={nw.days} min={1} onChange={(v) => setNw({ ...nw, days: Math.round(v) })} />
        </Field>
        <Field label={t('workers')}>
          <NumInput className="w-24" value={nw.workers} min={1} onChange={(v) => setNw({ ...nw, workers: Math.round(v) })} />
        </Field>
        <Field label={`${t('price')} (EUR)`}>
          <NumInput className="w-32" value={nw.price} min={0} onChange={(v) => setNw({ ...nw, price: v })} />
        </Field>
        <button type="button" className="btn-primary" onClick={() => save.mutate({ ...nw, active: true })} data-testid="button-add-labor">
          <Plus className="h-4 w-4" /> {t('add')}
        </button>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------- roof types
function RoofsTab({ lang }: { lang: string }) {
  const { t } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const roofs = useQuery({ queryKey: ['roof-types', 'all'], queryFn: () => get<RoofType[]>('/api/catalog/roof-types?include_inactive=true') })
  const save = useMutation({
    mutationFn: (r: RoofType) => put(`/api/catalog/roof-types/${r.code}`, r),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['roof-types'] })
      qc.invalidateQueries({ queryKey: ['quotes'] })
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const [edit, setEdit] = useState<RoofType | null>(null)
  const [isNew, setIsNew] = useState(false)
  const systems = useMountingSystems()
  const sysFor = (code: string) => systems.data?.systems.find((x) => x.code === systems.data?.roof_system[code])
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-2">{lang === 'bg' ? 'Типът покрив определя монтажната система, брой шини на модул и начина на ценообразуване на конструкцията.' : 'The roof type defines the mounting system, rails per module and how the structure is priced.'}</p>
        <button
          type="button"
          className="btn-accent btn-sm"
          onClick={() => {
            setIsNew(true)
            setEdit({ code: '', label_bg: '', label_en: '', pricing_mode: 'detailed', lump_price_per_module: 0, rails_per_module: 2, rail_stock_length_m: 3.55, fixation_spacing_m: 1.2, waste_pct: 8, default_tilt_deg: 20, kind: null, notes: '', sort_order: 99, active: true })
          }}
        >
          <Plus className="h-4 w-4" /> {t('add')}
        </button>
      </div>
      {roofs.isLoading && <Loading />}
      <div className="card overflow-x-auto">
        <table className="tbl min-w-[900px]">
          <thead>
            <tr>
              <th>{t('name')}</th>
              <th>code</th>
              <th>{t('mounting_system')}</th>
              <th>{t('mounting')}</th>
              <th className="text-right">{t('rails')}/mod</th>
              <th className="text-right">{lang === 'bg' ? 'Шина m' : 'Rail m'}</th>
              <th className="text-right">{lang === 'bg' ? 'Стъпка куки m' : 'Hook spacing m'}</th>
              <th className="text-right">{lang === 'bg' ? 'Фира %' : 'Waste %'}</th>
              <th className="text-right">{lang === 'bg' ? 'Обща цена/мод' : 'Lump/mod'}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(roofs.data || []).map((r) => (
              <tr key={r.code} className={cx(!r.active && 'opacity-50')}>
                <td className="font-medium">{lang === 'bg' ? r.label_bg : r.label_en}</td>
                <td className="font-mono text-xs text-ink-3">{r.code}</td>
                <td>
                  {(() => {
                    const sy = sysFor(r.code)
                    if (!sy) return <span className="text-ink-3">—</span>
                    return (
                      <div className="flex flex-col gap-1">
                        <span className="text-xs font-medium">
                          AEROCOMPACT {sy.family} {sy.code}
                        </span>
                        <DocLinks docs={Object.fromEntries(Object.entries(sy.docs).filter(([k]) => ['leaflet', 'leaflet_s10', 'assembly', 'assembly_uk'].includes(k)))} compact />
                      </div>
                    )
                  })()}
                </td>
                <td>
                  <Badge tone={r.pricing_mode === 'lump' ? 'sun' : 'neutral'}>{r.pricing_mode === 'lump' ? t('mounting_lump') : t('mounting_detailed')}</Badge>
                </td>
                <td className="num text-right">{r.rails_per_module}</td>
                <td className="num text-right">{r.rail_stock_length_m}</td>
                <td className="num text-right">{r.fixation_spacing_m}</td>
                <td className="num text-right">{r.waste_pct}</td>
                <td className="num text-right">{r.lump_price_per_module ? fmtMoney(r.lump_price_per_module) : '—'}</td>
                <td className="text-right">
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    onClick={() => {
                      setIsNew(false)
                      setEdit(r)
                    }}
                  >
                    {t('edit')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edit && (
        <Modal
          open
          onClose={() => setEdit(null)}
          title={edit.label_bg || t('roof_type')}
          footer={
            <>
              <button type="button" className="btn-ghost" onClick={() => setEdit(null)}>
                {t('cancel')}
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={!edit.code || !edit.label_bg}
                onClick={() => {
                  save.mutate(edit)
                  setEdit(null)
                }}
              >
                {t('save')}
              </button>
            </>
          }
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="code" hint="a-z, _">
              <Input value={edit.code} disabled={!isNew} onChange={(e) => setEdit({ ...edit, code: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })} />
            </Field>
            <Field label={t('mounting')}>
              <Select value={edit.pricing_mode} onChange={(e) => setEdit({ ...edit, pricing_mode: e.target.value })}>
                <option value="detailed">{t('mounting_detailed')}</option>
                <option value="lump">{t('mounting_lump')}</option>
              </Select>
            </Field>
            <Field label="BG">
              <Input value={edit.label_bg} onChange={(e) => setEdit({ ...edit, label_bg: e.target.value })} />
            </Field>
            <Field label="EN">
              <Input value={edit.label_en} onChange={(e) => setEdit({ ...edit, label_en: e.target.value })} />
            </Field>
            <Field label={`${t('rails')} / ${t('modules').toLowerCase()}`}>
              <NumInput value={edit.rails_per_module} min={1} max={4} onChange={(v) => setEdit({ ...edit, rails_per_module: Math.round(v) })} />
            </Field>
            <Field label={lang === 'bg' ? 'Дължина шина (m)' : 'Rail stock length (m)'}>
              <NumInput value={edit.rail_stock_length_m} min={0.5} onChange={(v) => setEdit({ ...edit, rail_stock_length_m: v })} />
            </Field>
            <Field label={lang === 'bg' ? 'Стъпка куки/крепежи (m)' : 'Fixation spacing (m)'}>
              <NumInput value={edit.fixation_spacing_m} min={0.2} onChange={(v) => setEdit({ ...edit, fixation_spacing_m: v })} />
            </Field>
            <Field label={lang === 'bg' ? 'Фира %' : 'Waste %'}>
              <NumInput value={edit.waste_pct} min={0} onChange={(v) => setEdit({ ...edit, waste_pct: v })} />
            </Field>
            <Field label={`${t('mounting_lump')} (EUR)`}>
              <NumInput value={edit.lump_price_per_module} min={0} onChange={(v) => setEdit({ ...edit, lump_price_per_module: v })} />
            </Field>
            <Field label={t('roof_kind')}>
              <Select value={edit.kind || ''} onChange={(e) => setEdit({ ...edit, kind: e.target.value || null })} data-testid="select-roof-kind">
                <option value="">{lang === 'bg' ? '— по кода —' : '— from code —'}</option>
                {SITE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`kind_${k}`)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t('tilt')}>
              <NumInput value={edit.default_tilt_deg} min={0} max={90} onChange={(v) => setEdit({ ...edit, default_tilt_deg: v })} />
            </Field>
            <Field label={t('notes')} className="col-span-2">
              <Input value={edit.notes || ''} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} />
            </Field>
            <Toggle checked={edit.active} onChange={(v) => setEdit({ ...edit, active: v })} label={t('active')} />
          </div>
        </Modal>
      )}
    </div>
  )
}

// ----------------------------------------------------------------- mounting rules
function RulesTab({ lang }: { lang: string }) {
  const { t } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [roof, setRoof] = useState('tile')
  const roofs = useQuery({ queryKey: ['roof-types'], queryFn: () => get<RoofType[]>('/api/catalog/roof-types') })
  const rules = useQuery({ queryKey: ['mounting-rules', roof], queryFn: () => get<MountingRule[]>(`/api/catalog/mounting-rules?roof_type=${roof}`) })
  const items = useQuery({ queryKey: ['catalog', 'items', false], queryFn: () => get<CatalogItem[]>('/api/catalog/items') })
  const meta = useQuery({ queryKey: ['catalog', 'meta'], queryFn: () => get<Meta>('/api/catalog/meta') })
  const mounting = (items.data || []).filter((i) => i.category === 'mounting')
  const inv = () => {
    qc.invalidateQueries({ queryKey: ['mounting-rules'] })
    qc.invalidateQueries({ queryKey: ['quotes'] })
  }
  const save = useMutation({
    mutationFn: (r: Partial<MountingRule>) => (r.id ? put(`/api/catalog/mounting-rules/${r.id}`, r) : post('/api/catalog/mounting-rules', r)),
    onSuccess: inv,
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({ mutationFn: (id: number) => del(`/api/catalog/mounting-rules/${id}`), onSuccess: inv, onError: (e) => toast.push(errMsg(e), 'bad') })
  const bases = meta.data?.mounting_bases || []
  const baseLabel = (code: string) => label(BASIS_LABELS, code, lang)
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-2">
        {lang === 'bg'
          ? 'Всяко правило изчислява количество = база × коефициент. Бази: модули, шини (бр.), метри шина, фиксатори (куки), средни/крайни скоби, съединители, стрингове, фиксирано. Правилата се прилагат автоматично в офертата според типа покрив.'
          : 'Each rule computes quantity = basis × factor. Bases: modules, rail pieces, rail metres, fixations (hooks), mid/end clamps, connectors, strings, fixed. Rules are applied automatically in the quote based on roof type.'}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={roof} onChange={(e) => setRoof(e.target.value)} className="w-auto" aria-label={t('roof_type')}>
          {(roofs.data || []).map((r) => (
            <option key={r.code} value={r.code}>
              {lang === 'bg' ? r.label_bg : r.label_en}
            </option>
          ))}
        </Select>
        <button type="button" className="btn-accent btn-sm ml-auto" onClick={() => save.mutate({ roof_type: roof, name: lang === 'bg' ? 'Ново правило' : 'New rule', basis: 'per_module', factor: 1, round_up: true, active: true, catalog_item_id: mounting[0]?.id ?? null, sort_order: 99 })} data-testid="button-add-rule">
          <Plus className="h-4 w-4" /> {t('add')}
        </button>
      </div>
      {rules.isLoading && <Loading />}
      <div className="card overflow-x-auto">
        <table className="tbl min-w-[800px]">
          <thead>
            <tr>
              <th>{t('name')}</th>
              <th>{lang === 'bg' ? 'Артикул' : 'Catalog item'}</th>
              <th>{lang === 'bg' ? 'База' : 'Basis'}</th>
              <th className="w-24 text-right">×</th>
              <th>{lang === 'bg' ? 'Закр. нагоре' : 'Round up'}</th>
              <th>{t('active')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(rules.data || []).map((r) => (
              <tr key={r.id}>
                <td>
                  <input className="cell-input min-w-[10rem]" defaultValue={r.name} key={`${r.id}-${r.name}`} onBlur={(e) => e.target.value !== r.name && save.mutate({ ...r, name: e.target.value })} />
                </td>
                <td>
                  <Select className="input-sm" value={r.catalog_item_id ?? ''} onChange={(e) => save.mutate({ ...r, catalog_item_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{t('none')}</option>
                    {mounting.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </Select>
                </td>
                <td>
                  <Select className="input-sm" value={r.basis} onChange={(e) => save.mutate({ ...r, basis: e.target.value })}>
                    {bases.map((b) => (
                      <option key={b} value={b}>
                        {baseLabel(b)}
                      </option>
                    ))}
                  </Select>
                </td>
                <td>
                  <NumInput className="cell-input" value={r.factor} onChange={(v) => v !== r.factor && save.mutate({ ...r, factor: v })} />
                </td>
                <td>
                  <Toggle checked={r.round_up} onChange={(v) => save.mutate({ ...r, round_up: v })} />
                </td>
                <td>
                  <Toggle checked={r.active} onChange={(v) => save.mutate({ ...r, active: v })} />
                </td>
                <td className="text-right">
                  <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => remove.mutate(r.id)} aria-label={t('delete')}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
