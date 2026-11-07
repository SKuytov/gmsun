import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Save, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, ErrorBox, Field, Input, Loading, Modal, NumInput, Select, Textarea, Toggle, cx, useToast } from '@/components/ui'
import { api, errMsg, fileUrl, get, getServerUrl, patch, post, put, setServerUrl } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useT } from '@/lib/i18n'
import type { CompanySettings, PricingSettings, ProcurementSettings, SupplierCfg, SuppliersSettings, TextsSettings, User } from '@/lib/types'

const TABS = ['company', 'pricing', 'suppliers', 'texts', 'users', 'server'] as const
type Tab = (typeof TABS)[number]

export default function SettingsPage() {
  const { t } = useT()
  const { tab: tabParam } = useParams()
  const nav = useNavigate()
  const { user } = useAuth()
  const admin = user?.role === 'admin'
  const tabs = TABS.filter((x) => admin || x === 'users' || x === 'server')
  const tab: Tab = (tabs as readonly string[]).includes(tabParam || '') ? (tabParam as Tab) : tabs[0]
  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1>{t('settings_title')}</h1>
        <div className="inline-flex flex-wrap gap-1 rounded-md bg-surface-2 p-1">
          {tabs.map((x) => (
            <button key={x} type="button" onClick={() => nav(`/settings/${x}`)} className={cx('h-9 rounded px-3 text-sm font-medium', tab === x ? 'bg-surface shadow-card' : 'text-ink-2')} data-testid={`tab-settings-${x}`}>
              {{ company: t('company'), pricing: t('pricing'), suppliers: t('suppliers_tab'), texts: t('texts'), users: admin ? t('users') : t('change_password'), server: t('server') }[x]}
            </button>
          ))}
        </div>
      </div>
      {tab === 'company' && <CompanyTab />}
      {tab === 'pricing' && <PricingTab />}
      {tab === 'suppliers' && <SuppliersTab />}
      {tab === 'texts' && <TextsTab />}
      {tab === 'users' && <UsersTab admin={admin} />}
      {tab === 'server' && <ServerTab />}
    </div>
  )
}

function useSetting<T extends object>(key: string) {
  const qc = useQueryClient()
  const toast = useToast()
  const { t } = useT()
  const q = useQuery({ queryKey: ['settings', key], queryFn: () => get<{ key: string; value: T }>(`/api/settings/${key}`).then((r) => r.value) })
  const [draft, setDraft] = useState<T | null>(null)
  useEffect(() => {
    if (q.data) setDraft(q.data)
  }, [q.data])
  const save = useMutation({
    mutationFn: (v: T) => put<{ key: string; value: T }>(`/api/settings/${key}`, { value: v }),
    onSuccess: (r) => {
      qc.setQueryData(['settings', key], r.value)
      qc.invalidateQueries({ queryKey: ['settings'] })
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const dirty = !!draft && !!q.data && JSON.stringify(draft) !== JSON.stringify(q.data)
  return { q, draft, setDraft, save, dirty }
}

function SaveBar({ dirty, busy, onSave }: { dirty: boolean; busy: boolean; onSave: () => void }) {
  const { t } = useT()
  return (
    <div className="flex justify-end">
      <button type="button" className="btn-primary" disabled={!dirty || busy} onClick={onSave} data-testid="button-save-settings">
        <Save className="h-4 w-4" /> {t('save')}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------- company
function CompanyTab() {
  const { t, lang } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { q, draft, setDraft, save, dirty } = useSetting<CompanySettings>('company')
  const ref = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  if (!draft) return q.isError ? <ErrorBox>{errMsg(q.error)}</ErrorBox> : <Loading />
  const set = (k: keyof CompanySettings, v: string) => setDraft({ ...draft, [k]: v })
  const upload = async (file: File) => {
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api<{ value: CompanySettings }>('/api/settings/company/logo', { form: fd })
      qc.setQueryData(['settings', 'company'], r.value)
      toast.push(t('saved'), 'ok')
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setUploading(false)
    }
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="card grid grid-cols-1 gap-3 p-4 sm:grid-cols-2">
        <Field label={t('company')} className="sm:col-span-2">
          <Input value={draft.name} onChange={(e) => set('name', e.target.value)} data-testid="input-company-name" />
        </Field>
        <Field label={t('address')} className="sm:col-span-2">
          <Input value={draft.address} onChange={(e) => set('address', e.target.value)} />
        </Field>
        <Field label="ЕИК">
          <Input value={draft.eik} onChange={(e) => set('eik', e.target.value)} />
        </Field>
        <Field label={lang === 'bg' ? 'ДДС №' : 'VAT no.'}>
          <Input value={draft.vat_no} onChange={(e) => set('vat_no', e.target.value)} />
        </Field>
        <Field label={t('phone')}>
          <Input value={draft.phone} onChange={(e) => set('phone', e.target.value)} />
        </Field>
        <Field label={t('email')}>
          <Input value={draft.email} onChange={(e) => set('email', e.target.value)} />
        </Field>
        <Field label={lang === 'bg' ? 'Уебсайт' : 'Website'}>
          <Input value={draft.website} onChange={(e) => set('website', e.target.value)} />
        </Field>
        <Field label={t('signatory')}>
          <Input value={draft.signatory} onChange={(e) => set('signatory', e.target.value)} />
        </Field>
        <Field label={lang === 'bg' ? 'Банка' : 'Bank'}>
          <Input value={draft.bank} onChange={(e) => set('bank', e.target.value)} />
        </Field>
        <Field label="IBAN">
          <Input value={draft.iban} onChange={(e) => set('iban', e.target.value)} />
        </Field>
      </div>
      <div className="card flex flex-wrap items-center gap-4 p-4">
        <div className="flex h-20 w-40 items-center justify-center rounded-md bg-surface-2">
          {draft.logo_path ? <img src={fileUrl(draft.logo_path)} alt={t('logo')} className="max-h-16 max-w-[9rem] object-contain" /> : <span className="text-xs text-ink-3">{t('logo')}</span>}
        </div>
        <input ref={ref} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        <button type="button" className="btn-ghost" onClick={() => ref.current?.click()} disabled={uploading}>
          <Upload className="h-4 w-4" /> {t('upload_logo')}
        </button>
        <p className="text-xs text-ink-3">{lang === 'bg' ? 'PNG/JPG/SVG. Показва се в заглавието на PDF офертата.' : 'PNG/JPG/SVG. Shown in the PDF quote header.'}</p>
      </div>
      <SaveBar dirty={dirty} busy={save.isPending} onSave={() => save.mutate(draft)} />
    </div>
  )
}

// ---------------------------------------------------------------- pricing
function PricingTab() {
  const { t, lang } = useT()
  const { q, draft, setDraft, save, dirty } = useSetting<PricingSettings>('pricing')
  if (!draft) return q.isError ? <ErrorBox>{errMsg(q.error)}</ErrorBox> : <Loading />
  const num = (k: keyof PricingSettings, label: string, hint?: string, step?: number) => (
    <Field label={label} hint={hint}>
      <NumInput value={draft[k] as number} step={step} onChange={(v) => setDraft({ ...draft, [k]: v })} />
    </Field>
  )
  const bg = lang === 'bg'
  return (
    <div className="flex flex-col gap-4">
      <div className="card grid grid-cols-2 gap-3 p-4 sm:grid-cols-3">
        <Field label={t('currency')}>
          <Input value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })} />
        </Field>
        {num('vat_pct', t('vat'))}
        {num('default_markup_pct', `${t('markup')} (${bg ? 'по подразбиране' : 'default'})`, bg ? 'Прилага се върху доставната цена на артикули без собствена надценка' : 'Applied to purchase price of items without their own markup')}
        {num('default_advance_pct', `${t('advance')} (${bg ? 'по подразбиране' : 'default'})`)}
        <Field label={bg ? 'Опции за аванс' : 'Advance options'} hint={bg ? 'през запетая' : 'comma separated'}>
          <Input
            defaultValue={draft.advance_options.join(', ')}
            onBlur={(e) =>
              setDraft({
                ...draft,
                advance_options: e.target.value
                  .split(/[,\s]+/)
                  .map(Number)
                  .filter((n) => n > 0 && n <= 100),
              })
            }
          />
        </Field>
        <Field label={bg ? 'База за аванса' : 'Advance basis'}>
          <Select value={draft.advance_basis} onChange={(e) => setDraft({ ...draft, advance_basis: e.target.value as 'net' | 'total' })}>
            <option value="net">{bg ? 'без ДДС' : 'net (excl. VAT)'}</option>
            <option value="total">{bg ? 'с ДДС' : 'total (incl. VAT)'}</option>
          </Select>
        </Field>
        {num('quote_validity_days', t('validity'))}
        <Field label={bg ? 'Префикс на номера' : 'Quote number prefix'} hint={bg ? 'напр. GM- → GM-261107-01PV' : 'e.g. GM- → GM-261107-01PV'}>
          <Input value={draft.quote_number_prefix} onChange={(e) => setDraft({ ...draft, quote_number_prefix: e.target.value })} />
        </Field>
      </div>
      <div className="card grid grid-cols-2 gap-3 p-4 sm:grid-cols-3">
        {num('install_price_per_w', `${t('labor')} €/W`, bg ? 'за режим „по мощност“' : 'for "per W" labor mode', 0.001)}
        {num('delivery_fee_equipment', bg ? 'Доставка оборудване' : 'Delivery: equipment')}
        {num('delivery_fee_inverter', bg ? 'Доставка инвертор' : 'Delivery: inverter')}
        {num('delivery_fee_construction', bg ? 'Доставка конструкция' : 'Delivery: structure')}
        {num('specific_yield_kwh_per_kwp', bg ? 'Специф. добив kWh/kWp' : 'Specific yield kWh/kWp', bg ? 'за оценка на годишното производство' : 'for the annual yield estimate')}
        {num('dc_ac_ratio_max', 'DC/AC max', bg ? 'праг за предупреждение при оразмеряване' : 'warning threshold when sizing', 0.05)}
      </div>
      <div className="card flex flex-col gap-3 p-4">
        <h2>{t('engineering_defaults')}</h2>
        <p className="text-xs text-ink-3">{bg ? 'Индустриални резерви и проектни граници за автоматичната спецификация (IEC 62548 / IEC 60364-7-712). Резервът за кабели покрива отрязъци и трасета, а за дребни крепежи — загуби при монтаж.' : 'Industry margins and design limits for the automatic BOM (IEC 62548 / IEC 60364-7-712). The cable margin covers off-cuts and routing; the fastener margin covers losses on site.'}</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {num('cable_margin_pct', t('cable_margin_pct'), bg ? 'типично 10–20 %' : 'typically 10–20 %')}
          {num('fastener_margin_pct', t('fastener_margin_pct'), bg ? 'типично 5–10 %' : 'typically 5–10 %')}
          {num('module_spare_pct', t('module_spare_pct'), bg ? '0 = без резервни' : '0 = no spares')}
          {num('design_tmin_c', t('design_tmin_c'), bg ? 'за Voc на стринга' : 'for string Voc')}
          {num('design_tcell_max_c', t('design_tcell_max_c'), bg ? 'за Vmp на стринга' : 'for string Vmp')}
          {num('dc_vdrop_max_pct', t('dc_vdrop_max_pct'), undefined, 0.1)}
          {num('ac_vdrop_max_pct', t('ac_vdrop_max_pct'), undefined, 0.1)}
          {num('dc_run_default_m', t('dc_run_default_m'))}
          {num('ac_run_default_m', t('ac_run_default_m'))}
          {num('dc_box_distance_m', t('dc_box_distance_m'), bg ? 'IEC 61643-32: SPD при масива над 10 m' : 'IEC 61643-32: SPD at the array above 10 m')}
        </div>
      </div>
      <div className="card flex flex-col gap-2 p-4">
        <Toggle checked={draft.show_unit_prices_client} onChange={(v) => setDraft({ ...draft, show_unit_prices_client: v })} label={bg ? 'Единични цени в клиентския PDF' : 'Unit prices in client PDF'} />
        <Toggle checked={draft.client_pdf_collapse_construction} onChange={(v) => setDraft({ ...draft, client_pdf_collapse_construction: v })} label={bg ? 'Конструкцията като един ред в клиентския PDF' : 'Collapse structure into one line in client PDF'} />
      </div>
      <SaveBar dirty={dirty} busy={save.isPending} onSave={() => save.mutate(draft)} />
    </div>
  )
}

// ---------------------------------------------------------------- texts
function TextsTab() {
  const { lang } = useT()
  const { q, draft, setDraft, save, dirty } = useSetting<TextsSettings>('texts')
  if (!draft) return q.isError ? <ErrorBox>{errMsg(q.error)}</ErrorBox> : <Loading />
  const bg = lang === 'bg'
  const area = (k: keyof TextsSettings, label: string, rows = 4) => (
    <Field label={label}>
      <Textarea rows={rows} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
    </Field>
  )
  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-col gap-3 p-4">
        {area('quote_title', bg ? 'Заглавие на офертата' : 'Quote title', 2)}
        {area('intro', bg ? 'Уводен текст към клиента (първа страница)' : 'Introduction to the client (first page)', 3)}
        {area('warranty', bg ? 'Гаранционни условия' : 'Warranty terms')}
        {area('payment', bg ? 'Условия на плащане' : 'Payment terms')}
        {area('notes', bg ? 'Забележки' : 'Notes')}
        {area('closing', bg ? 'Заключителен текст' : 'Closing text', 2)}
        {area('rfq_note', bg ? 'Текст в запитванията към доставчици' : 'Text in supplier requests', 2)}
        <p className="text-xs text-ink-3">{bg ? 'Всеки ред се показва като отделен абзац в PDF.' : 'Each line becomes a separate paragraph in the PDF.'}</p>
      </div>
      <SaveBar dirty={dirty} busy={save.isPending} onSave={() => save.mutate(draft)} />
    </div>
  )
}

// ---------------------------------------------------------------- suppliers / procurement
function SuppliersTab() {
  const { t, lang } = useT()
  const bg = lang === 'bg'
  const sup = useSetting<SuppliersSettings>('suppliers')
  const proc = useSetting<ProcurementSettings>('procurement')
  if (!sup.draft || !proc.draft) return sup.q.isError ? <ErrorBox>{errMsg(sup.q.error)}</ErrorBox> : <Loading />
  const d = sup.draft
  const pd = proc.draft
  const setRow = (i: number, patch: Partial<SupplierCfg>) => sup.setDraft({ ...d, list: d.list.map((r, j) => (j === i ? { ...r, ...patch } : r)) })
  const listArea = (key: 'premium' | 'economy', label: string) => (
    <Field label={label} hint={bg ? 'по един производител на ред или през запетая' : 'one brand per line or comma-separated'}>
      <Textarea
        rows={4}
        value={pd.brand_tiers[key].join(', ')}
        onChange={(e) =>
          proc.setDraft({
            ...pd,
            brand_tiers: {
              ...pd.brand_tiers,
              [key]: e.target.value
                .split(/[,\n]/)
                .map((x) => x.trim())
                .filter(Boolean),
            },
          })
        }
      />
    </Field>
  )
  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-col gap-3 p-4" data-testid="suppliers-card">
        <div>
          <h2>{t('suppliers_tab')}</h2>
          <p className="text-sm text-ink-2">{bg ? 'Срокът на доставка на артикул = срок на артикула (ако е зададен) → срок на доставчика → общ срок по подразбиране. Срокът на цялата оферта е най-дългият срок сред позициите ѝ.' : 'Item lead time = item override → supplier default → global default. The quote lead time is the longest among its lines.'}</p>
        </div>
        <div className="overflow-x-auto">
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('supplier')}</th>
                <th>{bg ? 'Контакт' : 'Contact'}</th>
                <th>E-mail</th>
                <th>{bg ? 'Телефон' : 'Phone'}</th>
                <th className="w-28 text-right">{t('lead_time_days')}</th>
                <th>{t('notes')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {d.list.map((r, i) => (
                <tr key={i}>
                  <td>
                    <Input className="input-sm" value={r.name} onChange={(e) => setRow(i, { name: e.target.value })} data-testid={`input-supplier-name-${i}`} />
                  </td>
                  <td>
                    <Input className="input-sm" value={r.contact || ''} onChange={(e) => setRow(i, { contact: e.target.value })} />
                  </td>
                  <td>
                    <Input className="input-sm" value={r.email || ''} onChange={(e) => setRow(i, { email: e.target.value })} />
                  </td>
                  <td>
                    <Input className="input-sm" value={r.phone || ''} onChange={(e) => setRow(i, { phone: e.target.value })} />
                  </td>
                  <td>
                    <NumInput className="input-sm" value={r.lead_time_days ?? null} min={0} onChange={(v) => setRow(i, { lead_time_days: v == null ? null : Math.round(v) })} />
                  </td>
                  <td>
                    <Input className="input-sm" value={r.notes || ''} onChange={(e) => setRow(i, { notes: e.target.value })} />
                  </td>
                  <td className="text-right">
                    <button type="button" className="btn-quiet btn-sm" onClick={() => sup.setDraft({ ...d, list: d.list.filter((_, j) => j !== i) })} aria-label={t('delete')}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <button type="button" className="btn-ghost btn-sm" onClick={() => sup.setDraft({ ...d, list: [...d.list, { name: '', lead_time_days: d.default_lead_time_days }] })} data-testid="button-add-supplier">
            <Plus className="h-4 w-4" /> {t('add')}
          </button>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={bg ? 'Срок по подразбиране (раб. дни)' : 'Default lead time (working days)'}>
            <NumInput value={d.default_lead_time_days} min={0} onChange={(v) => sup.setDraft({ ...d, default_lead_time_days: Math.round(v || 0) })} />
          </Field>
          <Field label={bg ? 'Срок при „по поръчка“ (раб. дни)' : 'Back-order lead time (working days)'}>
            <NumInput value={d.backorder_lead_time_days} min={0} onChange={(v) => sup.setDraft({ ...d, backorder_lead_time_days: Math.round(v || 0) })} />
          </Field>
          <Field label={bg ? 'Адрес за доставка (в запитванията)' : 'Delivery address (in RFQs)'} hint={bg ? 'празно = адрес на фирмата' : 'empty = company address'}>
            <Input value={d.delivery_address || ''} onChange={(e) => sup.setDraft({ ...d, delivery_address: e.target.value })} />
          </Field>
        </div>
        <SaveBar dirty={sup.dirty} busy={sup.save.isPending} onSave={() => sup.save.mutate(d)} />
      </div>

      <div className="card flex flex-col gap-3 p-4">
        <div>
          <h2>{bg ? 'Класове и автоматични предложения' : 'Tiers and automatic proposals'}</h2>
          <p className="text-sm text-ink-2">{bg ? 'Класът на артикул (икономичен / стандартен / премиум) се определя автоматично от цената за единица (€/Wp, €/kW, €/kWh), марката и качествени показатели (КПД, гаранция, цикли). Ръчно зададен клас в Каталог има предимство.' : 'Item tier (economy / standard / premium) is derived from unit price (€/Wp, €/kW, €/kWh), brand and quality signals (efficiency, warranty, cycles). A manual tier in the Catalog wins.'}</p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {listArea('premium', bg ? 'Премиум марки' : 'Premium brands')}
          {listArea('economy', bg ? 'Икономични марки' : 'Economy brands')}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label={bg ? 'Тежест цена' : 'Weight: price'}>
            <NumInput value={pd.tier_weights.price} min={0} onChange={(v) => proc.setDraft({ ...pd, tier_weights: { ...pd.tier_weights, price: v || 0 } })} />
          </Field>
          <Field label={bg ? 'Тежест марка' : 'Weight: brand'}>
            <NumInput value={pd.tier_weights.brand} min={0} onChange={(v) => proc.setDraft({ ...pd, tier_weights: { ...pd.tier_weights, brand: v || 0 } })} />
          </Field>
          <Field label={bg ? 'Тежест качество' : 'Weight: quality'}>
            <NumInput value={pd.tier_weights.quality} min={0} onChange={(v) => proc.setDraft({ ...pd, tier_weights: { ...pd.tier_weights, quality: v || 0 } })} />
          </Field>
          <Field label={bg ? '„Балансиран“: € за ден доставка' : 'Balanced: € per delivery day'} hint={bg ? 'колко струва един ден чакане при сравнение' : 'cost of one waiting day when ranking'}>
            <NumInput value={pd.balanced_eur_per_day} min={0} onChange={(v) => proc.setDraft({ ...pd, balanced_eur_per_day: v || 0 })} />
          </Field>
          <Field label={bg ? 'Кандидати: модули' : 'Candidates: modules'}>
            <NumInput value={pd.candidate_panels} min={1} onChange={(v) => proc.setDraft({ ...pd, candidate_panels: Math.round(v || 1) })} />
          </Field>
          <Field label={bg ? 'Кандидати: инвертори' : 'Candidates: inverters'}>
            <NumInput value={pd.candidate_inverters} min={1} onChange={(v) => proc.setDraft({ ...pd, candidate_inverters: Math.round(v || 1) })} />
          </Field>
          <Field label={bg ? 'Кандидати: батерии' : 'Candidates: batteries'}>
            <NumInput value={pd.candidate_batteries} min={1} onChange={(v) => proc.setDraft({ ...pd, candidate_batteries: Math.round(v || 1) })} />
          </Field>
        </div>
        <SaveBar dirty={proc.dirty} busy={proc.save.isPending} onSave={() => proc.save.mutate(pd)} />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- users
function UsersTab({ admin }: { admin: boolean }) {
  const { t, lang } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user: me } = useAuth()
  const users = useQuery({ queryKey: ['users'], queryFn: () => get<User[]>('/api/auth/users'), enabled: admin })
  const [creating, setCreating] = useState(false)
  const [nu, setNu] = useState({ email: '', name: '', password: '', role: 'user' })
  const [pw, setPw] = useState({ old: '', new: '', new2: '' })
  const inv = () => qc.invalidateQueries({ queryKey: ['users'] })
  const create = useMutation({
    mutationFn: () => post<User>('/api/auth/users', nu),
    onSuccess: () => {
      inv()
      setCreating(false)
      setNu({ email: '', name: '', password: '', role: 'user' })
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const update = useMutation({ mutationFn: ({ id, ...b }: { id: number; role?: string; active?: boolean; password?: string; name?: string }) => patch<User>(`/api/auth/users/${id}`, b), onSuccess: inv, onError: (e) => toast.push(errMsg(e), 'bad') })
  const changePw = useMutation({
    mutationFn: () => post('/api/auth/change-password', { old: pw.old, new: pw.new }),
    onSuccess: () => {
      setPw({ old: '', new: '', new2: '' })
      toast.push(t('saved'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const bg = lang === 'bg'
  return (
    <div className="flex flex-col gap-4">
      {admin && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between p-3">
            <h2>{t('users')}</h2>
            <button type="button" className="btn-accent btn-sm" onClick={() => setCreating(true)} data-testid="button-new-user">
              <Plus className="h-4 w-4" /> {t('new_user')}
            </button>
          </div>
          {users.isLoading && <Loading />}
          <table className="tbl">
            <thead>
              <tr>
                <th>{t('email')}</th>
                <th>{t('name')}</th>
                <th>{t('role')}</th>
                <th>{t('active')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(users.data || []).map((u) => (
                <tr key={u.id} className={cx(!u.active && 'opacity-50')}>
                  <td className="font-medium">
                    {u.email} {u.id === me?.id && <Badge tone="sun">{bg ? 'аз' : 'me'}</Badge>}
                  </td>
                  <td>
                    <input className="cell-input" defaultValue={u.name} key={`${u.id}-${u.name}`} onBlur={(e) => e.target.value !== u.name && update.mutate({ id: u.id, name: e.target.value })} aria-label={t('name')} />
                  </td>
                  <td>
                    <Select className="input-sm w-auto" value={u.role} disabled={u.id === me?.id} onChange={(e) => update.mutate({ id: u.id, role: e.target.value })}>
                      <option value="admin">{t('role_admin')}</option>
                      <option value="user">{t('role_user')}</option>
                    </Select>
                  </td>
                  <td>
                    <Toggle checked={u.active} disabled={u.id === me?.id} onChange={(v) => update.mutate({ id: u.id, active: v })} />
                  </td>
                  <td className="text-right">
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={() => {
                        const p = window.prompt(bg ? `Нова парола за ${u.email} (мин. 6 символа)` : `New password for ${u.email} (min 6 chars)`)
                        if (p && p.length >= 6) update.mutate({ id: u.id, password: p })
                      }}
                    >
                      {t('change_password')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="card flex flex-col gap-3 p-4">
        <h2>{t('change_password')}</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Field label={bg ? 'Текуща парола' : 'Current password'}>
            <Input type="password" autoComplete="current-password" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} />
          </Field>
          <Field label={bg ? 'Нова парола' : 'New password'}>
            <Input type="password" autoComplete="new-password" value={pw.new} onChange={(e) => setPw({ ...pw, new: e.target.value })} />
          </Field>
          <Field label={bg ? 'Повтори' : 'Repeat'} error={pw.new2 && pw.new2 !== pw.new ? (bg ? 'Паролите не съвпадат' : 'Passwords differ') : undefined}>
            <Input type="password" autoComplete="new-password" value={pw.new2} onChange={(e) => setPw({ ...pw, new2: e.target.value })} />
          </Field>
        </div>
        <div className="flex justify-end">
          <button type="button" className="btn-primary" disabled={!pw.old || pw.new.length < 6 || pw.new !== pw.new2 || changePw.isPending} onClick={() => changePw.mutate()}>
            {t('change_password')}
          </button>
        </div>
      </div>
      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title={t('new_user')}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
              {t('cancel')}
            </button>
            <button type="button" className="btn-primary" disabled={!nu.email || nu.password.length < 6 || create.isPending} onClick={() => create.mutate()} data-testid="button-save-user">
              {t('save')}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t('email')} className="sm:col-span-2">
            <Input type="email" value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} data-testid="input-user-email" />
          </Field>
          <Field label={t('name')}>
            <Input value={nu.name} onChange={(e) => setNu({ ...nu, name: e.target.value })} />
          </Field>
          <Field label={t('role')}>
            <Select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}>
              <option value="user">{t('role_user')}</option>
              <option value="admin">{t('role_admin')}</option>
            </Select>
          </Field>
          <Field label={t('password')} hint={bg ? 'минимум 6 символа' : 'min 6 characters'} className="sm:col-span-2">
            <Input type="password" autoComplete="new-password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} data-testid="input-user-password" />
          </Field>
        </div>
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------- server
function ServerTab() {
  const { t, lang } = useT()
  const toast = useToast()
  const [url, setUrl] = useState(getServerUrl())
  const [status, setStatus] = useState<'idle' | 'ok' | 'bad'>('idle')
  const test = async () => {
    try {
      const base = url.replace(/\/+$/, '')
      const r = await fetch(`${base}/api/health`)
      setStatus(r.ok ? 'ok' : 'bad')
    } catch {
      setStatus('bad')
    }
  }
  return (
    <div className="card flex flex-col gap-3 p-4">
      <Field label={t('server_url')} hint={t('server_url_hint')}>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://192.168.1.50" data-testid="input-server-url" />
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-ghost" onClick={test}>
          {lang === 'bg' ? 'Провери връзката' : 'Test connection'}
        </button>
        {status === 'ok' && <Badge tone="ok">OK</Badge>}
        {status === 'bad' && <Badge tone="bad">{lang === 'bg' ? 'Няма връзка' : 'No connection'}</Badge>}
        <button
          type="button"
          className="btn-primary ml-auto"
          onClick={async () => {
            await setServerUrl(url)
            toast.push(t('saved'), 'ok')
            window.location.reload()
          }}
        >
          <Save className="h-4 w-4" /> {t('save')}
        </button>
      </div>
      <p className="text-xs text-ink-3">{lang === 'bg' ? 'Използва се от Android приложението, за да знае къде е инсталиран сървърът на gmsun. Браузърната версия работи без настройка.' : 'Used by the Android app to find the gmsun server. The browser version needs no setting.'}</p>
    </div>
  )
}
