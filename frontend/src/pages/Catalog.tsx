import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Download, Plus, Search, Trash2, Upload } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Confirm, ErrorBox, Field, Input, Loading, Modal, NumInput, Select, Textarea, Toggle, cx, useToast } from '@/components/ui'
import { api, del, downloadFile, errMsg, get, patch, post, put } from '@/lib/api'
import { fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { CatalogItem, LaborOption, MountingRule, RoofType } from '@/lib/types'
import { useAuth } from '@/lib/auth'

const TABS = ['items', 'labor', 'roofs', 'rules'] as const
type Tab = (typeof TABS)[number]

interface Meta {
  categories: { code: string; label_bg: string; label_en: string }[]
  bases?: { code: string; label_bg: string; label_en: string }[]
}

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
              {{ items: t('nav_catalog'), labor: t('labor'), roofs: t('roof_types_title'), rules: t('mounting_rules_title') }[x]}
            </button>
          ))}
        </div>
      </div>
      {tab === 'items' && <ItemsTab lang={lang} />}
      {tab === 'labor' && <LaborTab />}
      {tab === 'roofs' && <RoofsTab lang={lang} />}
      {tab === 'rules' && <RulesTab lang={lang} />}
    </div>
  )
}

// ----------------------------------------------------------------- items
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
  const items = useQuery({ queryKey: ['catalog', 'items', inactive], queryFn: () => get<CatalogItem[]>(`/api/catalog/items${inactive ? '?include_inactive=true' : ''}`) })
  const meta = useQuery({ queryKey: ['catalog', 'meta'], queryFn: () => get<Meta>('/api/catalog/meta') })
  const invalidate = () => qc.invalidateQueries({ queryKey: ['catalog'] })

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
  const catLabel = (code: string) => {
    const c = meta.data?.categories.find((x) => x.code === code)
    return c ? (lang === 'bg' ? c.label_bg : c.label_en) : code
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={cat} onChange={(e) => setCat(e.target.value)} className="w-auto" aria-label={t('category')} data-testid="select-category">
          <option value="">{t('all')}</option>
          {(meta.data?.categories || []).map((c) => (
            <option key={c.code} value={c.code}>
              {lang === 'bg' ? c.label_bg : c.label_en}
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
            <button type="button" className="btn-ghost btn-sm" onClick={() => setImportOpen(true)} data-testid="button-import">
              <Upload className="h-4 w-4" /> {t('import_xlsx')}
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => downloadFile('/api/catalog/export', 'gmsun-catalog.xlsx').catch((e) => toast.push(errMsg(e), 'bad'))}>
              <Download className="h-4 w-4" /> {t('export_xlsx')}
            </button>
            <button type="button" className="btn-accent btn-sm" onClick={() => setEditing({ category: cat || 'panel', unit: 'бр.', purchase_price: 0, active: true, specs: {} })} data-testid="button-new-item">
              <Plus className="h-4 w-4" /> {t('new_item')}
            </button>
          </div>
        )}
      </div>
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
                    </td>
                    <td className="text-ink-2">{i.manufacturer}</td>
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
      <Confirm open={!!toDelete} onClose={() => setToDelete(null)} onConfirm={() => toDelete && remove.mutate(toDelete.id)} title={t('delete')} text={`${t('confirm_delete')} ${toDelete?.name}`} danger />
    </div>
  )
}

function ItemModal({ item, meta, onClose, onSave, busy }: { item: Partial<CatalogItem>; meta?: Meta; onClose: () => void; onSave: (it: Partial<CatalogItem>) => void; busy: boolean }) {
  const { t, lang } = useT()
  const [f, setF] = useState<Partial<CatalogItem>>({ ...item })
  const [specs, setSpecs] = useState(JSON.stringify(item.specs || {}, null, 2))
  const [specsErr, setSpecsErr] = useState('')
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
              <option key={c.code} value={c.code}>
                {lang === 'bg' ? c.label_bg : c.label_en}
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
        <Field label={t('active')} className="self-end">
          <Toggle checked={f.active !== false} onChange={(v) => setF({ ...f, active: v })} />
        </Field>
        <Field label={t('notes')} className="sm:col-span-3">
          <Input value={f.description || ''} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        {f.category && commonSpecs[f.category] && <div className="grid grid-cols-2 gap-3 sm:col-span-3 sm:grid-cols-4">{commonSpecs[f.category]}</div>}
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
              <option key={c.code} value={c.code}>
                {lang === 'bg' ? c.label_bg : c.label_en}
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

// ----------------------------------------------------------------- labor
function LaborTab() {
  const { t, lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const labor = useQuery({ queryKey: ['labor', 'all'], queryFn: () => get<LaborOption[]>('/api/catalog/labor?include_inactive=true') })
  const inv = () => {
    qc.invalidateQueries({ queryKey: ['labor'] })
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
        <table className="tbl">
          <thead>
            <tr>
              <th>
                {t('days')} \ {t('workers')}
              </th>
              {workers.map((w) => (
                <th key={w} className="text-center">
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
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const [edit, setEdit] = useState<RoofType | null>(null)
  const [isNew, setIsNew] = useState(false)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-2">{lang === 'bg' ? 'Типът покрив определя монтажната система, брой шини на модул и начина на ценообразуване на конструкцията.' : 'The roof type defines the mounting system, rails per module and how the structure is priced.'}</p>
        <button
          type="button"
          className="btn-accent btn-sm"
          onClick={() => {
            setIsNew(true)
            setEdit({ code: '', label_bg: '', label_en: '', pricing_mode: 'detailed', lump_price_per_module: 0, rails_per_module: 2, rail_stock_length_m: 3.55, fixation_spacing_m: 1.2, waste_pct: 8, default_tilt_deg: 20, notes: '', sort_order: 99, active: true })
          }}
        >
          <Plus className="h-4 w-4" /> {t('add')}
        </button>
      </div>
      {roofs.isLoading && <Loading />}
      <div className="card overflow-x-auto">
        <table className="tbl min-w-[720px]">
          <thead>
            <tr>
              <th>{t('name')}</th>
              <th>code</th>
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
  const inv = () => qc.invalidateQueries({ queryKey: ['mounting-rules'] })
  const save = useMutation({
    mutationFn: (r: Partial<MountingRule>) => (r.id ? put(`/api/catalog/mounting-rules/${r.id}`, r) : post('/api/catalog/mounting-rules', r)),
    onSuccess: inv,
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({ mutationFn: (id: number) => del(`/api/catalog/mounting-rules/${id}`), onSuccess: inv, onError: (e) => toast.push(errMsg(e), 'bad') })
  const bases = meta.data?.bases || []
  const baseLabel = (code: string) => {
    const b = bases.find((x) => x.code === code)
    return b ? (lang === 'bg' ? b.label_bg : b.label_en) : code
  }
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
                      <option key={b.code} value={b.code}>
                        {baseLabel(b.code)}
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
