import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Ban, Check, ExternalLink, FileText, ShieldCheck, TriangleAlert } from 'lucide-react'
import { Badge, Field, Loading, NumInput, Select, Toggle, Warn, cx, useToast } from '@/components/ui'
import { downloadFile, errMsg, get } from '@/lib/api'
import { fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { BatterySuggestion, CatalogItem, CompatEntry, CompatMatrix, InverterSuggestion } from '@/lib/types'
import type { StepCtx } from '../Project'
import { Proposals } from './Proposals'
import { ModuleAdvisor } from '@/components/ModuleAdvisor'
import { BatteryParts } from '@/components/BatteryParts'
import type { Selections } from '@/lib/types'

/** Datasheet / supplier page links + unverified-specs hint for a catalog item. */
function ItemLinks({ item }: { item: CatalogItem | undefined }) {
  const { t } = useT()
  const toast = useToast()
  if (!item) return null
  const ds = !!(item.specs.datasheet_url || item.specs.datasheet_file)
  const url = typeof item.specs.product_url === 'string' ? item.specs.product_url : ''
  const unverified = item.specs.specs_verified === false && !!item.specs.spec_source
  if (!ds && !url && !unverified) return null
  return (
    <span className="mt-1 flex flex-wrap items-center gap-1" onClick={(e) => e.stopPropagation()}>
      {ds && (
        <button type="button" className="btn-ghost btn-sm" onClick={() => downloadFile(`/api/catalog/items/${item.id}/datasheet`, `${(item.sku || item.name).slice(0, 60)}.pdf`).catch((e) => toast.push(errMsg(e), 'bad'))} data-testid={`button-datasheet-${item.id}`}>
          <FileText className="h-3.5 w-3.5" /> {t('datasheet')}
        </button>
      )}
      {url && (
        <a href={url} target="_blank" rel="noreferrer" className="btn-ghost btn-sm">
          <ExternalLink className="h-3.5 w-3.5" /> {t('product_page')}
        </a>
      )}
      {unverified && (
        <span className="text-xs text-warn" title={t('specs_unverified_hint')}>
          {t('specs_unverified')}
        </span>
      )}
    </span>
  )
}

/** ok / warn / blocked marker from the compatibility engine (reasons in the tooltip and below the card). */
export function CompatBadge({ c, compact }: { c: CompatEntry | undefined; compact?: boolean }) {
  const { lang } = useT()
  if (!c) return null
  const label =
    c.status === 'blocked' ? (lang === 'bg' ? 'Несъвместимо' : 'Incompatible') : c.status === 'warn' ? (lang === 'bg' ? 'С бележки' : 'With notes') : lang === 'bg' ? 'Съвместимо' : 'Compatible'
  const Icon = c.status === 'blocked' ? Ban : c.status === 'warn' ? TriangleAlert : ShieldCheck
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium',
        c.status === 'blocked' ? 'bg-bad/10 text-bad' : c.status === 'warn' ? 'bg-warn/10 text-warn' : 'bg-ok/10 text-ok',
      )}
      title={c.reasons.join('\n') || label}
      data-testid={`compat-${c.status}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {!compact && label}
    </span>
  )
}

function ItemCard({ item, selected, onSelect, lines, warnings, extra, compat }: { item: CatalogItem; selected: boolean; onSelect: () => void; lines: string[]; warnings: string[]; extra?: React.ReactNode; compat?: CompatEntry }) {
  const blocked = compat?.status === 'blocked'
  const pick = () => {
    if (!blocked) onSelect()
  }
  return (
    <div
      role="button"
      tabIndex={blocked ? -1 : 0}
      onClick={pick}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), pick())}
      className={cx(
        'card flex w-full items-start gap-3 p-3 text-left transition',
        blocked ? 'cursor-not-allowed opacity-60' : 'cursor-pointer hover:border-ink/30',
        selected && (blocked ? 'border-bad ring-2 ring-bad/30 opacity-100' : 'border-sun ring-2 ring-sun/30'),
      )}
      aria-pressed={selected}
      aria-disabled={blocked || undefined}
      data-testid={`card-item-${item.id}`}
    >
      <span className={cx('mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border', selected ? 'border-sun bg-sun text-ink' : 'border-line/30')}>{selected && <Check className="h-3.5 w-3.5" />}</span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-medium leading-tight">{item.name}</span>
          {item.id ? <CompatBadge c={compat} /> : null}
        </span>
        <span className="mt-0.5 block text-xs text-ink-3">{lines.join(' · ')}</span>
        {extra}
        {warnings.length > 0 && <span className="mt-1 block text-xs text-warn">{warnings.join('; ')}</span>}
        {compat && compat.status !== 'ok' && compat.reasons.length > 0 && (
          <span className={cx('mt-1 block text-xs', compat.status === 'blocked' ? 'text-bad' : 'text-warn')}>{compat.reasons.join(' ')}</span>
        )}
        {item.id ? <ItemLinks item={item} /> : null}
      </span>
      <span className="num shrink-0 text-right text-sm font-semibold">{item.effective_price > 0 ? fmtMoney(item.effective_price) : <span className="text-ink-3">—</span>}</span>
    </div>
  )
}

export function EquipmentStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const { project: p, sel, setSel, items } = ctx
  const panels = items.filter((i) => i.category === 'panel')
  const inverters = items.filter((i) => i.category === 'inverter')
  const batteries = items.filter((i) => i.category === 'battery')
  const layoutCount = p.layouts.reduce((s, l) => s + (l.summary?.count || 0), 0)
  const useLayout = sel.use_layout !== false && layoutCount > 0
  const panelId = sel.panel_item_id || p.layouts[0]?.panel_item_id || panels[0]?.id
  // Persist the implicit default so kWp, sizing and the quote all use the same module.
  useEffect(() => {
    if (!sel.panel_item_id && panelId) setSel({ panel_item_id: panelId })
  }, [sel.panel_item_id, panelId, setSel])

  const invQ = useQuery({
    queryKey: ['sizing', 'inv', p.phase, p.connected_power_kw, ctx.kwp, p.voltage_class],
    queryFn: () => get<InverterSuggestion[]>(`/api/sizing/inverters?phase=${p.phase}&connected_kw=${p.connected_power_kw}&pv_kwp=${ctx.kwp}&voltage_class=${p.voltage_class}`),
  })
  const batQ = useQuery({
    queryKey: ['sizing', 'bat', sel.inverter_item_id, p.desired_storage_kwh, p.voltage_class],
    queryFn: () => get<BatterySuggestion[]>(`/api/sizing/batteries?${sel.inverter_item_id ? `inverter_id=${sel.inverter_item_id}&` : ''}target_kwh=${p.desired_storage_kwh}&voltage_class=${p.voltage_class}`),
  })
  const invQty = Math.max(1, Math.round(sel.inverter_qty || 1))
  const stringsQ = useQuery({
    queryKey: ['sizing', 'strings', panelId, sel.inverter_item_id, ctx.panelQty, invQty],
    queryFn: () => get<Record<string, number | string[] | { strings: number }[]>>(`/api/sizing/strings?panel_id=${panelId}&inverter_id=${sel.inverter_item_id}&n_panels=${ctx.panelQty}&n_inverters=${invQty}`),
    enabled: !!panelId && !!sel.inverter_item_id && ctx.panelQty > 0,
  })

  const batQty = Math.max(0, Math.round(sel.battery_qty || 0))
  const compatQ = useQuery({
    queryKey: ['compat', p.id, panelId, sel.inverter_item_id, invQty, ctx.panelQty, sel.battery_item_id, batQty, p.phase],
    queryFn: () => {
      const q = new URLSearchParams()
      if (panelId) q.set('panel_item_id', String(panelId))
      if (sel.inverter_item_id) q.set('inverter_item_id', String(sel.inverter_item_id))
      q.set('inverter_qty', String(invQty))
      q.set('panel_qty', String(ctx.panelQty || 0))
      if (sel.battery_item_id) q.set('battery_item_id', String(sel.battery_item_id))
      q.set('battery_qty', String(batQty))
      return get<CompatMatrix>(`/api/projects/${p.id}/compatibility?${q}`)
    },
  })
  const cm = compatQ.data
  const cInv = (id: number) => cm?.inverters[String(id)]
  const cPanel = (id: number) => cm?.panels[String(id)]
  const cBat = (id: number) => cm?.batteries[String(id)]
  const toast = useToast()

  // Keep the system connectable: after an inverter change an incompatible battery is replaced by the best compatible
  // suggestion, and the battery count is clamped to what the inverter / BMS accepts. (Runs once per compat result.)
  const fixedFor = useRef('')
  useEffect(() => {
    if (!cm || compatQ.isFetching || !sel.battery_item_id || !batQ.data) return
    const key = `${sel.inverter_item_id}|${sel.battery_item_id}|${batQty}|${invQty}`
    if (fixedFor.current === key) return
    const c = cm.batteries[String(sel.battery_item_id)]
    if (!c || c.status !== 'blocked') return
    fixedFor.current = key
    const r = c.range
    const name = batteries.find((b) => b.id === sel.battery_item_id)?.name || ''
    if (r && r.max >= r.min && r.max > 0) {
      // the model is usable, only the count is wrong -> clamp to the allowed range
      const allowed = r.max
      const q = Math.min(Math.max(batQty, r.min), allowed)
      if (q !== batQty && q > 0) {
        setSel({ battery_qty: q })
        toast.push(lang === 'bg' ? `Брой батерии коригиран на ${q} (допустимо ${r.min}–${allowed} за този инвертор).` : `Battery count set to ${q} (allowed ${r.min}–${allowed} for this inverter).`, 'ok')
        return
      }
    }
    const best = (batQ.data || []).find((b) => cBat(b.item.id)?.status !== 'blocked')
    if (best) {
      setSel({ battery_item_id: best.item.id, battery_qty: best.qty, battery_accessories: [], battery_bms: { mode: 'auto', items: [] }, battery_rack: { mode: 'auto', items: [] } })
      toast.push(lang === 'bg' ? `„${name}“ не е съвместима с инвертора — заменена с „${best.item.name}“ × ${best.qty}.` : `"${name}" is not compatible with the inverter — replaced by "${best.item.name}" × ${best.qty}.`, 'ok')
    } else {
      setSel({ battery_item_id: null, battery_qty: 0, battery_accessories: [], battery_bms: { mode: 'auto', items: [] }, battery_rack: { mode: 'auto', items: [] } })
      toast.push(lang === 'bg' ? `„${name}“ не е съвместима с инвертора и е премахната.` : `"${name}" is not compatible with the inverter and was removed.`, 'bad')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cm, compatQ.isFetching, batQ.data, sel.battery_item_id, sel.inverter_item_id, batQty, invQty])

  const pickInverter = (id: number, suggestedQty?: number) => {
    const c = cInv(id)
    const qty = Math.max(1, suggestedQty || 1, c?.qty || 1)
    // keep the battery; the effect above swaps it only if it cannot work with the new inverter
    setSel({ inverter_item_id: id, inverter_qty: qty })
  }

  const invSug = invQ.data || []
  const asSug = (item: CatalogItem): InverterSuggestion => ({ item, qty: 1, ac_total_kw: Number(item.specs.ac_power_kw || 0), ratio: 0, score: 0, reasons: [], warnings: [] })
  const selInv = inverters.find((i) => i.id === sel.inverter_item_id)
  // the chosen inverter is always shown as a card, even when it is outside the suggestions (e.g. HV on an LV project)
  const shownInv: InverterSuggestion[] = invSug.length
    ? (selInv && !invSug.some((s) => s.item.id === selInv.id) ? [asSug(selInv), ...invSug] : invSug)
    : inverters.map(asSug)
  const selInvSug = invSug.find((s) => s.item.id === sel.inverter_item_id)
  const invAc = Number(selInv?.specs?.ac_power_kw || 0)
  const dcAc = invAc > 0 ? ctx.kwp / (invAc * invQty) : 0
  const otherInv = inverters.filter((i) => !shownInv.some((s) => s.item.id === i.id))
  const batSugRaw = batQ.data || []
  const selBatItem = batteries.find((b) => b.id === sel.battery_item_id)
  // keep the chosen battery visible as a card even when it is not among the suggestions
  const batSug: BatterySuggestion[] =
    selBatItem && !batSugRaw.some((s) => s.item.id === selBatItem.id)
      ? [{ item: selBatItem, qty: sel.battery_qty || 1, total_kwh: Number(selBatItem.specs.kwh || 0) * (sel.battery_qty || 1), reasons: [], warnings: [], accessories: [] }, ...batSugRaw]
      : batSugRaw
  const otherBat = batteries.filter((i) => !batSug.some((s) => s.item.id === i.id))
  const selBat = batteries.find((b) => b.id === sel.battery_item_id)
  const batKwh = Number(selBat?.specs?.kwh || 0)

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <Proposals ctx={ctx} />
      </div>
      {/* panels */}
      <div className="card p-4 lg:col-span-2">
        <h2 className="mb-3">{t('section_modules')}</h2>
        {p.layouts.length > 0 && (
          <div className="mb-4">
            <ModuleAdvisor project={p} compact onApplied={(proj) => ctx.replaceSel((proj.params?.selections as Selections) || {})} />
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto_auto]">
          <Field label={t('panel_model')}>
            <Select value={panelId ?? ''} onChange={(e) => setSel({ panel_item_id: Number(e.target.value) })} data-testid="select-panel">
              {panels.map((x) => {
                const c = cPanel(x.id)
                const bad = c?.status === 'blocked' && x.id !== panelId
                return (
                  <option key={x.id} value={x.id} disabled={bad}>
                    {x.name} — {fmtMoney(x.effective_price)}
                    {c?.status === 'blocked' ? (lang === 'bg' ? ' — несъвместим с инвертора' : ' — incompatible with the inverter') : c?.status === 'warn' ? ' — !' : ''}
                  </option>
                )
              })}
            </Select>
            <ItemLinks item={panels.find((x) => x.id === panelId)} />
            {panelId && sel.inverter_item_id && cPanel(panelId) && (
              <span className="mt-1 flex flex-wrap items-center gap-2">
                <CompatBadge c={cPanel(panelId)} />
                {cPanel(panelId)!.window && (
                  <span className="text-xs text-ink-3">
                    {lang === 'bg' ? 'Стринг' : 'String'} {cPanel(panelId)!.window!.ns_min}–{cPanel(panelId)!.window!.ns_max} {lang === 'bg' ? 'модула' : 'modules'} · Voc(−) {fmtNum(cPanel(panelId)!.window!.voc_cold, 0)} V
                  </span>
                )}
              </span>
            )}
            {panelId && cPanel(panelId)?.status !== 'ok' && (cPanel(panelId)?.reasons.length || 0) > 0 && (
              <span className={cx('mt-1 block text-xs', cPanel(panelId)!.status === 'blocked' ? 'text-bad' : 'text-warn')}>{cPanel(panelId)!.reasons.join(' ')}</span>
            )}
          </Field>
          <Field label={t('panel_count')}>
            <div className="flex items-center gap-2">
              <NumInput value={useLayout ? ctx.panelQty : sel.panel_qty || 0} onChange={(v) => setSel({ panel_qty: Math.round(v), use_layout: false, panel_limit: null })} min={0} className="w-28" disabled={useLayout} data-testid="input-panel-qty" />
              <span className="num whitespace-nowrap text-sm text-ink-2">= {fmtNum(ctx.kwp, 2)} kWp</span>
            </div>
          </Field>
          <Field label=" ">
            <Toggle checked={useLayout} disabled={layoutCount === 0} onChange={(v) => setSel({ use_layout: v, panel_limit: null })} label={`${t('from_layout')} (${layoutCount})`} />
            {useLayout && (sel.panel_limit || 0) > 0 && (sel.panel_limit || 0) < layoutCount && (
              <button type="button" className="btn-ghost btn-sm mt-1" onClick={() => setSel({ panel_limit: null })} data-testid="button-clear-panel-limit">
                {lang === 'bg' ? `Офертирани ${sel.panel_limit} от ${layoutCount} модула — използвай целия покрив` : `Quoting ${sel.panel_limit} of ${layoutCount} modules — use the whole roof`}
              </button>
            )}
          </Field>
        </div>
      </div>

      {/* inverter */}
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2>{t('inverter')}</h2>
          <span className="text-xs text-ink-3">
            {t(p.phase === 1 ? 'phase_1' : 'phase_3')} · {p.connected_power_kw} kW · {p.voltage_class}
          </span>
        </div>
        {invQ.isLoading && <Loading />}
        <div className="flex flex-col gap-2">
          {[...shownInv]
            .sort((a, b) => Number(cInv(a.item.id)?.status === 'blocked') - Number(cInv(b.item.id)?.status === 'blocked'))
            .map((s) => (
            <ItemCard
              key={s.item.id}
              item={s.item}
              compat={cInv(s.item.id)}
              selected={sel.inverter_item_id === s.item.id}
              onSelect={() => pickInverter(s.item.id, s.qty)}
              extra={s.qty > 1 ? <span className="mt-1 inline-block rounded bg-sun-soft px-1.5 py-0.5 text-xs font-medium text-sun-ink" data-testid={`inv-qty-${s.item.id}`}>{s.qty} × {lang === 'bg' ? 'в паралел' : 'in parallel'} = {fmtNum(s.ac_total_kw, 1)} kW AC</span> : undefined}
              lines={[
                `${s.item.specs.ac_power_kw ?? '?'} kW AC`,
                `${s.item.specs.max_pv_kw ?? '?'} kWp max`,
                `${s.item.specs.mppt_count ?? '?'} MPPT`,
                String(s.item.specs.battery_voltage_class || ''),
                ...s.reasons,
              ].filter(Boolean)}
              warnings={s.warnings}
            />
          ))}
          {otherInv.length > 0 && (
            <Field label={lang === 'bg' ? 'Други инвертори' : 'Other inverters'}>
              <Select value="" onChange={(e) => e.target.value && pickInverter(Number(e.target.value))} data-testid="select-other-inverter">
                <option value="">{t('none')}</option>
                {otherInv.map((x) => {
                  const c = cInv(x.id)
                  return (
                    <option key={x.id} value={x.id} disabled={c?.status === 'blocked'}>
                      {x.name}
                      {c?.status === 'blocked' ? ` — ${c.reasons[0] || (lang === 'bg' ? 'несъвместим' : 'incompatible')}` : c?.qty && c.qty > 1 ? ` — ${c.qty} ×` : ''}
                    </option>
                  )
                })}
              </Select>
            </Field>
          )}
        </div>
        {sel.inverter_item_id && (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[auto_1fr]">
            <Field label={t('inverter_qty')}>
              <NumInput value={invQty} min={1} max={16} step={1} onChange={(v) => setSel({ inverter_qty: Math.max(1, Math.round(v)) })} className="w-24" data-testid="input-inverter-qty" />
            </Field>
            <div className="self-end pb-1 text-xs text-ink-2">
              {invAc > 0 && (
                <>
                  <span className="num font-medium">{invQty > 1 ? `${invQty} × ${fmtNum(invAc, 1)} = ` : ''}{fmtNum(invAc * invQty, 1)} kW AC</span>
                  {ctx.kwp > 0 && (
                    <>
                      {' · '}DC/AC <span className={cx('num font-medium', dcAc > 1.35 || dcAc < 0.8 ? 'text-warn' : '')}>{fmtNum(dcAc, 2)}</span>
                    </>
                  )}
                  {selInvSug && selInvSug.qty !== invQty && (
                    <button type="button" className="btn-ghost btn-sm ml-2" onClick={() => setSel({ inverter_qty: selInvSug.qty })} data-testid="button-inverter-qty-suggest">
                      {t('inverter_qty_suggest')}: {selInvSug.qty}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )}
        {cm?.selected && cm.selected.blocked.length > 0 && (
          <div className="mt-3 rounded border border-bad/30 bg-bad/5 p-2 text-xs text-bad" data-testid="compat-system-blocked">
            <div className="mb-1 font-semibold">{lang === 'bg' ? 'Системата не може да бъде свързана така:' : 'This system cannot be connected:'}</div>
            <ul className="list-disc pl-4">
              {cm.selected.blocked.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        {stringsQ.data && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Badge tone="neutral">
              {t('strings')}: {String(stringsQ.data.strings)} × {String(stringsQ.data.modules_per_string)}
              {invQty > 1
                ? (() => {
                    const per = Array.isArray(stringsQ.data.per_inverter) ? (stringsQ.data.per_inverter as { strings: number }[]).map((x) => x.strings) : []
                    const lo = per.length ? Math.min(...per) : 0
                    const hi = per.length ? Math.max(...per) : 0
                    const n = lo === hi ? String(lo) : `${lo}–${hi}`
                    return lang === 'bg' ? ` · по ${n} на инвертор` : ` · ${n} per inverter`
                  })()
                : ''}
            </Badge>
            <Badge tone="neutral">MPPT: {String(stringsQ.data.mppts)}{invQty > 1 ? ` × ${invQty}` : ''}</Badge>
            {Array.isArray(stringsQ.data.warnings) && (stringsQ.data.warnings as string[]).map((w) => <Badge key={w} tone="warn">{w}</Badge>)}
          </div>
        )}
      </div>

      {/* battery */}
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2>{t('battery')}</h2>
          <span className="text-xs text-ink-3">{p.desired_storage_kwh} kWh</span>
        </div>
        {!sel.inverter_item_id && <Warn>{lang === 'bg' ? 'Изберете инвертор, за да се филтрират съвместимите батерии.' : 'Select an inverter to filter compatible batteries.'}</Warn>}
        {batQ.isLoading && <Loading />}
        <div className="mt-2 flex flex-col gap-2">
          <ItemCard
            item={{ id: 0, name: t('none'), category: 'battery', effective_price: 0, specs: {} } as unknown as CatalogItem}
            selected={!sel.battery_item_id}
            onSelect={() => setSel({ battery_item_id: null, battery_qty: 0, battery_accessories: [], battery_bms: { mode: 'auto', items: [] }, battery_rack: { mode: 'auto', items: [] } })}
            lines={[]}
            warnings={[]}
          />
          {batSug.map((s) => (
            <ItemCard
              key={s.item.id}
              item={s.item}
              compat={cBat(s.item.id)}
              selected={sel.battery_item_id === s.item.id}
              onSelect={() => sel.battery_item_id !== s.item.id && setSel({ battery_item_id: s.item.id, battery_qty: s.qty, battery_accessories: [], battery_bms: { mode: 'auto', items: [] }, battery_rack: { mode: 'auto', items: [] } })}
              lines={[`${s.item.specs.kwh} kWh`, String(s.item.specs.voltage_class || ''), `${s.qty} × = ${fmtNum(s.total_kwh, 1)} kWh`, ...s.reasons].filter(Boolean)}
              warnings={s.warnings}
            />
          ))}
          {otherBat.length > 0 && (
            <Field label={lang === 'bg' ? 'Други батерии' : 'Other batteries'}>
              <Select
                value=""
                onChange={(e) => {
                  if (!e.target.value) return
                  const id = Number(e.target.value)
                  const r = cBat(id)?.range
                  const q = Math.max(r?.min || 1, Math.min(sel.battery_qty || 1, r?.max || 99))
                  setSel({ battery_item_id: id, battery_qty: q, battery_accessories: [], battery_bms: { mode: 'auto', items: [] }, battery_rack: { mode: 'auto', items: [] } })
                }}
                data-testid="select-other-battery"
              >
                <option value="">{t('none')}</option>
                {otherBat.map((x) => {
                  const c = cBat(x.id)
                  return (
                    <option key={x.id} value={x.id} disabled={c?.status === 'blocked' && !c.range}>
                      {x.name} ({String(x.specs.kwh)} kWh, {String(x.specs.voltage_class)})
                      {c?.status === 'blocked' ? ` — ${c.reasons[0] || ''}` : ''}
                    </option>
                  )
                })}
              </Select>
            </Field>
          )}
        </div>
        {sel.battery_item_id ? (
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Field label={t('battery_qty')}>
              <NumInput
                value={sel.battery_qty || 1}
                min={cBat(sel.battery_item_id)?.range?.min || 1}
                max={cBat(sel.battery_item_id)?.range?.max || undefined}
                onChange={(v) => setSel({ battery_qty: Math.round(v) })}
                data-testid="input-battery-qty"
              />
              {cBat(sel.battery_item_id)?.range && (
                <span className="mt-1 block text-xs text-ink-3">
                  {lang === 'bg' ? 'Допустимо' : 'Allowed'}: {cBat(sel.battery_item_id)!.range!.min}–{cBat(sel.battery_item_id)!.range!.max}
                  {(cBat(sel.battery_item_id)!.range!.clusters?.length || 0) > 1 ? ` · ${cBat(sel.battery_item_id)!.range!.clusters!.join(' + ')}` : ''}
                </span>
              )}
              {cBat(sel.battery_item_id) && cBat(sel.battery_item_id)!.status !== 'ok' && (
                <span className={cx('mt-1 block text-xs', cBat(sel.battery_item_id)!.status === 'blocked' ? 'text-bad' : 'text-warn')}>{cBat(sel.battery_item_id)!.reasons.join(' ')}</span>
              )}
            </Field>
            <div className="self-end pb-2 text-sm text-ink-2">
              = <span className="num font-semibold">{fmtNum(batKwh * (sel.battery_qty || 1), 1)} kWh</span>
            </div>
            <BatteryParts sel={sel} setSel={setSel} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
