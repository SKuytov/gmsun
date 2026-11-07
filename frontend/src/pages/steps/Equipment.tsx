import { useQuery } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { Badge, Field, Loading, NumInput, Select, Toggle, Warn, cx } from '@/components/ui'
import { get } from '@/lib/api'
import { fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { BatterySuggestion, CatalogItem, InverterSuggestion } from '@/lib/types'
import type { StepCtx } from '../Project'

function ItemCard({ item, selected, onSelect, lines, warnings, extra }: { item: CatalogItem; selected: boolean; onSelect: () => void; lines: string[]; warnings: string[]; extra?: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cx('card flex w-full items-start gap-3 p-3 text-left transition hover:border-ink/30', selected && 'border-sun ring-2 ring-sun/30')}
      aria-pressed={selected}
      data-testid={`card-item-${item.id}`}
    >
      <span className={cx('mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border', selected ? 'border-sun bg-sun text-ink' : 'border-line/30')}>{selected && <Check className="h-3.5 w-3.5" />}</span>
      <span className="min-w-0 flex-1">
        <span className="block font-medium leading-tight">{item.name}</span>
        <span className="mt-0.5 block text-xs text-ink-3">{lines.join(' · ')}</span>
        {extra}
        {warnings.length > 0 && <span className="mt-1 block text-xs text-warn">{warnings.join('; ')}</span>}
      </span>
      <span className="num shrink-0 text-right text-sm font-semibold">{item.effective_price > 0 ? fmtMoney(item.effective_price) : <span className="text-ink-3">—</span>}</span>
    </button>
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

  const invQ = useQuery({
    queryKey: ['sizing', 'inv', p.phase, p.connected_power_kw, ctx.kwp, p.voltage_class],
    queryFn: () => get<InverterSuggestion[]>(`/api/sizing/inverters?phase=${p.phase}&connected_kw=${p.connected_power_kw}&pv_kwp=${ctx.kwp}&voltage_class=${p.voltage_class}`),
  })
  const batQ = useQuery({
    queryKey: ['sizing', 'bat', sel.inverter_item_id, p.desired_storage_kwh, p.voltage_class],
    queryFn: () => get<BatterySuggestion[]>(`/api/sizing/batteries?${sel.inverter_item_id ? `inverter_id=${sel.inverter_item_id}&` : ''}target_kwh=${p.desired_storage_kwh}&voltage_class=${p.voltage_class}`),
  })
  const stringsQ = useQuery({
    queryKey: ['sizing', 'strings', panelId, sel.inverter_item_id, ctx.panelQty],
    queryFn: () => get<Record<string, number | string[]>>(`/api/sizing/strings?panel_id=${panelId}&inverter_id=${sel.inverter_item_id}&n_panels=${ctx.panelQty}`),
    enabled: !!panelId && !!sel.inverter_item_id && ctx.panelQty > 0,
  })

  const invSug = invQ.data || []
  const shownInv = invSug.length ? invSug : inverters.map((item) => ({ item, score: 0, reasons: [], warnings: [] }))
  const otherInv = inverters.filter((i) => !shownInv.some((s) => s.item.id === i.id))
  const batSug = batQ.data || []
  const otherBat = batteries.filter((i) => !batSug.some((s) => s.item.id === i.id))
  const selBat = batteries.find((b) => b.id === sel.battery_item_id)
  const batKwh = Number(selBat?.specs?.kwh || 0)
  const selSug = batSug.find((b) => b.item.id === sel.battery_item_id)

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      {/* panels */}
      <div className="card p-4 lg:col-span-2">
        <h2 className="mb-3">{t('section_modules')}</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto_auto]">
          <Field label={t('panel_model')}>
            <Select value={panelId ?? ''} onChange={(e) => setSel({ panel_item_id: Number(e.target.value) })} data-testid="select-panel">
              {panels.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name} — {fmtMoney(x.effective_price)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('panel_count')}>
            <div className="flex items-center gap-2">
              <NumInput value={useLayout ? layoutCount : sel.panel_qty || 0} onChange={(v) => setSel({ panel_qty: Math.round(v), use_layout: false })} min={0} className="w-28" disabled={useLayout} data-testid="input-panel-qty" />
              <span className="num whitespace-nowrap text-sm text-ink-2">= {fmtNum(ctx.kwp, 2)} kWp</span>
            </div>
          </Field>
          <Field label=" ">
            <Toggle checked={useLayout} disabled={layoutCount === 0} onChange={(v) => setSel({ use_layout: v })} label={`${t('from_layout')} (${layoutCount})`} />
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
          {shownInv.map((s) => (
            <ItemCard
              key={s.item.id}
              item={s.item}
              selected={sel.inverter_item_id === s.item.id}
              onSelect={() => setSel({ inverter_item_id: s.item.id, battery_item_id: null, battery_accessories: [] })}
              lines={[
                `${s.item.specs.ac_power_kw ?? '?'} kW AC`,
                `${s.item.specs.max_pv_kw ?? '?'} kWp max`,
                `${s.item.specs.mppt_count ?? '?'} MPPT`,
                String(s.item.specs.battery_voltage_class || ''),
                ...s.reasons,
              ].filter(Boolean)}
              warnings={s.warnings}
              extra={s.item.specs.specs_verified === false ? <span className="mt-0.5 block text-xs text-ink-3">{lang === 'bg' ? 'Параметрите са ориентировъчни — проверете в каталога.' : 'Specs approximate — verify in catalog.'}</span> : null}
            />
          ))}
          {otherInv.length > 0 && (
            <Field label={lang === 'bg' ? 'Други инвертори' : 'Other inverters'}>
              <Select value="" onChange={(e) => e.target.value && setSel({ inverter_item_id: Number(e.target.value), battery_item_id: null })}>
                <option value="">{t('none')}</option>
                {otherInv.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
        {stringsQ.data && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <Badge tone="neutral">
              {t('strings')}: {String(stringsQ.data.strings)} × {String(stringsQ.data.modules_per_string)}
            </Badge>
            <Badge tone="neutral">MPPT: {String(stringsQ.data.mppts)}</Badge>
            {Array.isArray(stringsQ.data.warnings) && stringsQ.data.warnings.map((w) => <Badge key={w} tone="warn">{w}</Badge>)}
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
            onSelect={() => setSel({ battery_item_id: null, battery_qty: 0, battery_accessories: [] })}
            lines={[]}
            warnings={[]}
          />
          {batSug.map((s) => (
            <ItemCard
              key={s.item.id}
              item={s.item}
              selected={sel.battery_item_id === s.item.id}
              onSelect={() => setSel({ battery_item_id: s.item.id, battery_qty: s.qty, battery_accessories: s.accessories.map((a) => ({ item_id: a.item_id, qty: a.qty })) })}
              lines={[`${s.item.specs.kwh} kWh`, String(s.item.specs.voltage_class || ''), `${s.qty} × = ${fmtNum(s.total_kwh, 1)} kWh`, ...s.reasons].filter(Boolean)}
              warnings={s.warnings}
            />
          ))}
          {otherBat.length > 0 && (
            <Field label={lang === 'bg' ? 'Други батерии' : 'Other batteries'}>
              <Select value="" onChange={(e) => e.target.value && setSel({ battery_item_id: Number(e.target.value), battery_qty: sel.battery_qty || 1 })}>
                <option value="">{t('none')}</option>
                {otherBat.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name} ({String(x.specs.kwh)} kWh, {String(x.specs.voltage_class)})
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
        {sel.battery_item_id ? (
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Field label={t('battery_qty')}>
              <NumInput value={sel.battery_qty || 1} min={1} onChange={(v) => setSel({ battery_qty: Math.round(v) })} data-testid="input-battery-qty" />
            </Field>
            <div className="self-end pb-2 text-sm text-ink-2">
              = <span className="num font-semibold">{fmtNum(batKwh * (sel.battery_qty || 1), 1)} kWh</span>
            </div>
            {(selSug?.accessories.length || (sel.battery_accessories || []).length) > 0 && (
              <Field label={t('battery_accessories')} className="col-span-2">
                <ul className="flex flex-col gap-1 text-sm">
                  {(sel.battery_accessories || []).map((a, i) => {
                    const it = items.find((x) => x.id === a.item_id)
                    return (
                      <li key={i} className="flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate">{it?.name || a.item_id}</span>
                        <NumInput className="input-sm w-20" value={a.qty} min={0} onChange={(v) => setSel({ battery_accessories: (sel.battery_accessories || []).map((x, j) => (j === i ? { ...x, qty: v } : x)) })} />
                      </li>
                    )
                  })}
                </ul>
              </Field>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}
