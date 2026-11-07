import { Plus, Trash2 } from 'lucide-react'
import { Field, Input, NumInput, Segmented, Select, Toggle } from '@/components/ui'
import { fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { CatalogItem, Selections } from '@/lib/types'
import type { StepCtx } from '../Project'

function ItemSelect({ items, value, onChange, allowNone = true, label, testId }: { items: CatalogItem[]; value: number | null | undefined; onChange: (id: number | null) => void; allowNone?: boolean; label: string; testId?: string }) {
  const { t } = useT()
  return (
    <Field label={label}>
      <Select value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} data-testid={testId}>
        {allowNone && <option value="">{t('none')}</option>}
        {items.map((x) => (
          <option key={x.id} value={x.id}>
            {x.name} — {fmtMoney(x.effective_price)}/{x.unit}
          </option>
        ))}
      </Select>
    </Field>
  )
}

export function MaterialsStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const { sel, setSel, items, project: p } = ctx
  const by = (cat: string) => items.filter((i) => i.category === cat && i.active)
  const sb = by('switchboard').filter((x) => !x.specs.phases || Number(x.specs.phases) === p.phase)
  const roof = ctx.roofTypes.find((r) => r.code === p.roof_type)
  const electrical = by('electrical')
  const mounting = by('mounting')
  const extras = sel.extra_items || []
  const el = sel.electrical_items || []

  const setExtra = (i: number, patch: Partial<NonNullable<Selections['extra_items']>[number]>) => setSel({ extra_items: extras.map((x, j) => (j === i ? { ...x, ...patch } : x)) })

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="card flex flex-col gap-3 p-4">
        <h2>{t('section_electrical')}</h2>
        <ItemSelect label={`${t('switchboard')} (${t(p.phase === 1 ? 'phase_1' : 'phase_3')})`} items={sb.length ? sb : by('switchboard')} value={sel.switchboard_item_id} onChange={(v) => setSel({ switchboard_item_id: v })} testId="select-switchboard" />
        <ItemSelect label={t('solar_cable')} items={by('solar_cable')} value={sel.solar_cable_item_id} onChange={(v) => setSel({ solar_cable_item_id: v })} testId="select-solar-cable" />
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('red_m')}>
            <NumInput value={sel.solar_cable_red_m ?? 0} min={0} onChange={(v) => setSel({ solar_cable_red_m: v })} data-testid="input-red-m" />
          </Field>
          <Field label={t('black_m')}>
            <NumInput value={sel.solar_cable_black_m ?? 0} min={0} onChange={(v) => setSel({ solar_cable_black_m: v })} />
          </Field>
        </div>
        <div className="grid grid-cols-[1fr_7rem] gap-3">
          <ItemSelect label={t('mc4')} items={electrical.filter((x) => /mc4/i.test(x.name))} value={sel.mc4_item_id} onChange={(v) => setSel({ mc4_item_id: v })} />
          <Field label={t('qty')} hint={lang === 'bg' ? 'празно = авто' : 'empty = auto'}>
            <NumInput value={sel.mc4_qty ?? null} min={0} onChange={(v) => setSel({ mc4_qty: v })} />
          </Field>
        </div>
        <div className="grid grid-cols-[1fr_7rem] gap-3">
          <ItemSelect label={t('power_cable')} items={by('power_cable')} value={sel.power_cable_item_id} onChange={(v) => setSel({ power_cable_item_id: v })} testId="select-power-cable" />
          <Field label={t('length_m')}>
            <NumInput value={sel.power_cable_m ?? 0} min={0} onChange={(v) => setSel({ power_cable_m: v })} />
          </Field>
        </div>

        <h2 className="mt-2 text-base">{t('other_electrical')}</h2>
        <ul className="flex flex-col gap-2">
          {el.map((x, i) => {
            const it = items.find((q) => q.id === x.item_id)
            return (
              <li key={i} className="grid grid-cols-[1fr_6rem_auto] items-center gap-2">
                <Select className="input-sm" value={x.item_id} onChange={(e) => setSel({ electrical_items: el.map((y, j) => (j === i ? { ...y, item_id: Number(e.target.value) } : y)) })}>
                  {electrical.map((q) => (
                    <option key={q.id} value={q.id}>
                      {q.name}
                    </option>
                  ))}
                </Select>
                <NumInput className="input-sm" value={x.qty} min={0} onChange={(v) => setSel({ electrical_items: el.map((y, j) => (j === i ? { ...y, qty: v } : y)) })} />
                <span className="flex items-center gap-1 text-xs text-ink-3">
                  {it?.unit}
                  <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => setSel({ electrical_items: el.filter((_, j) => j !== i) })} aria-label={t('delete')}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </span>
              </li>
            )
          })}
        </ul>
        <button type="button" className="btn-ghost btn-sm self-start" onClick={() => electrical[0] && setSel({ electrical_items: [...el, { item_id: electrical[0].id, qty: 1 }] })}>
          <Plus className="h-4 w-4" /> {t('add')}
        </button>
      </div>

      <div className="flex flex-col gap-5">
        <div className="card flex flex-col gap-3 p-4">
          <h2>{t('mounting')}</h2>
          <p className="text-xs text-ink-3">
            {roof ? (lang === 'bg' ? roof.label_bg : roof.label_en) : p.roof_type} · {roof?.pricing_mode === 'lump' ? `${fmtMoney(roof.lump_price_per_module)} / ${t('modules').toLowerCase()}` : lang === 'bg' ? 'по правила за конструкция' : 'by mounting rules'}
          </p>
          <Segmented
            value={sel.mounting_mode || 'auto'}
            onChange={(v) => setSel({ mounting_mode: v })}
            options={[
              { value: 'auto', label: t('mounting_auto') },
              { value: 'detailed', label: t('mounting_detailed') },
              { value: 'lump', label: t('mounting_lump') },
              { value: 'none', label: t('mounting_none') },
            ]}
          />
          {sel.mounting_mode === 'lump' && (
            <Field label={`${t('mounting_lump')} (EUR)`}>
              <NumInput value={sel.lump_price_per_module ?? roof?.lump_price_per_module ?? 0} min={0} onChange={(v) => setSel({ lump_price_per_module: v })} />
            </Field>
          )}
          {mounting.length > 0 && (
            <p className="text-xs text-ink-3">
              {mounting.length} {lang === 'bg' ? 'артикула конструкция в каталога; количествата се изчисляват от разположението (шини, куки, скоби).' : 'mounting items in the catalog; quantities are derived from the layout (rails, hooks, clamps).'}
            </p>
          )}
        </div>

        <div className="card flex flex-col gap-3 p-4">
          <h2>{t('extra_items')}</h2>
          <ul className="flex flex-col gap-2">
            {extras.map((x, i) => (
              <li key={i} className="grid grid-cols-[1fr_4.5rem_4rem_6rem_auto] items-center gap-2">
                <Input className="input-sm" placeholder={t('name')} value={x.name} onChange={(e) => setExtra(i, { name: e.target.value })} />
                <NumInput className="input-sm" value={x.qty} min={0} onChange={(v) => setExtra(i, { qty: v })} />
                <Input className="input-sm" value={x.unit || 'бр.'} onChange={(e) => setExtra(i, { unit: e.target.value })} />
                <NumInput className="input-sm" value={x.unit_price} min={0} onChange={(v) => setExtra(i, { unit_price: v })} />
                <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => setSel({ extra_items: extras.filter((_, j) => j !== i) })} aria-label={t('delete')}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="btn-ghost btn-sm self-start" onClick={() => setSel({ extra_items: [...extras, { name: '', qty: 1, unit: 'бр.', unit_price: 0, section: 'other' }] })} data-testid="button-add-extra">
            <Plus className="h-4 w-4" /> {t('add')}
          </button>
        </div>
      </div>
    </div>
  )
}

export function LaborStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const { sel, setSel, labor, pricing } = ctx
  const mode = sel.labor_mode || 'matrix'
  const days = Array.from(new Set(labor.map((l) => l.days))).sort((a, b) => a - b)
  const workers = Array.from(new Set(labor.map((l) => l.workers))).sort((a, b) => a - b)
  const ppw = sel.install_price_per_w ?? pricing.install_price_per_w
  const watts = ctx.kwp * 1000

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="card flex flex-col gap-3 p-4">
        <h2>{t('labor')}</h2>
        <Segmented
          value={mode}
          onChange={(v) => setSel({ labor_mode: v })}
          options={[
            { value: 'matrix', label: t('labor_matrix') },
            { value: 'per_w', label: t('labor_per_w') },
            { value: 'manual', label: t('labor_manual') },
          ]}
        />
        {mode === 'matrix' && (
          <div className="overflow-x-auto">
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
                {days.map((dd) => (
                  <tr key={dd}>
                    <td className="num font-medium">{dd}</td>
                    {workers.map((w) => {
                      const o = labor.find((l) => l.days === dd && l.workers === w)
                      const active = o && sel.labor_option_id === o.id
                      return (
                        <td key={w} className="p-0.5 text-center">
                          {o ? (
                            <button
                              type="button"
                              onClick={() => setSel({ labor_option_id: o.id })}
                              className={`num h-10 w-full min-w-[5.5rem] rounded text-sm ${active ? 'bg-ink text-white' : 'bg-surface-2 hover:bg-sun-soft'}`}
                              aria-pressed={active}
                              data-testid={`labor-${dd}-${w}`}
                            >
                              {fmtNum(o.price, 0)}
                            </button>
                          ) : (
                            <span className="text-ink-3">—</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {mode === 'per_w' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label={`${t('labor_per_w')} (EUR/W)`}>
              <NumInput value={ppw} min={0} step={0.001} onChange={(v) => setSel({ install_price_per_w: v })} />
            </Field>
            <div className="self-end pb-2 text-sm text-ink-2">
              {fmtNum(watts, 0)} W × {ppw} = <span className="num font-semibold">{fmtMoney(watts * ppw)}</span>
            </div>
          </div>
        )}
        {mode === 'manual' && (
          <div className="grid grid-cols-[1fr_9rem] gap-3">
            <Field label={t('name')}>
              <Input value={sel.labor_name || ''} placeholder={lang === 'bg' ? 'Монтаж, пуск и настройка' : 'Installation and commissioning'} onChange={(e) => setSel({ labor_name: e.target.value })} />
            </Field>
            <Field label="EUR">
              <NumInput value={sel.labor_price ?? 0} min={0} onChange={(v) => setSel({ labor_price: v })} />
            </Field>
          </div>
        )}
        <div className="grid grid-cols-[1fr_9rem] gap-3">
          <Field label={t('transport')}>
            <Input value={sel.transport_name || ''} placeholder={t('transport')} onChange={(e) => setSel({ transport_name: e.target.value })} />
          </Field>
          <Field label="EUR">
            <NumInput value={sel.transport_price ?? 0} min={0} onChange={(v) => setSel({ transport_price: v })} />
          </Field>
        </div>
        <Toggle checked={sel.delivery_fees !== false} onChange={(v) => setSel({ delivery_fees: v })} label={`${t('delivery_fees')} (${pricing.delivery_fee_equipment} / ${pricing.delivery_fee_inverter} / ${pricing.delivery_fee_construction} EUR)`} />
      </div>

      <div className="card flex flex-col gap-3 p-4">
        <h2>{lang === 'bg' ? 'Търговски условия' : 'Commercial terms'}</h2>
        <p className="text-xs text-ink-3">{lang === 'bg' ? 'Стойностите по подразбиране идват от Настройки → Ценообразуване и могат да се променят за всяка оферта.' : 'Defaults come from Settings → Pricing and can be overridden per quote.'}</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('markup')}>
            <NumInput value={(sel as Record<string, unknown>).markup_pct as number ?? pricing.default_markup_pct} min={0} onChange={(v) => setSel({ markup_pct: v } as Partial<Selections>)} />
          </Field>
          <Field label={t('discount')}>
            <NumInput value={((sel as Record<string, unknown>).discount_pct as number) ?? 0} min={0} max={100} onChange={(v) => setSel({ discount_pct: v } as Partial<Selections>)} />
          </Field>
          <Field label={t('vat')}>
            <NumInput value={((sel as Record<string, unknown>).vat_pct as number) ?? pricing.vat_pct} min={0} onChange={(v) => setSel({ vat_pct: v } as Partial<Selections>)} />
          </Field>
          <Field label={t('validity')}>
            <NumInput value={((sel as Record<string, unknown>).valid_days as number) ?? pricing.quote_validity_days} min={1} onChange={(v) => setSel({ valid_days: Math.round(v) } as Partial<Selections>)} />
          </Field>
          <Field label={t('advance')} className="col-span-2">
            <div className="flex flex-wrap items-center gap-2">
              <Segmented
                value={String(((sel as Record<string, unknown>).advance_pct as number) ?? pricing.default_advance_pct)}
                onChange={(v) => setSel({ advance_pct: Number(v) } as Partial<Selections>)}
                options={pricing.advance_options.map((a) => ({ value: String(a), label: `${a} %` }))}
              />
              <NumInput className="w-24" value={((sel as Record<string, unknown>).advance_pct as number) ?? pricing.default_advance_pct} min={0} max={100} onChange={(v) => setSel({ advance_pct: v } as Partial<Selections>)} />
            </div>
          </Field>
          <Field label={lang === 'bg' ? 'Аванс върху' : 'Advance basis'} className="col-span-2">
            <Segmented
              value={sel.advance_basis || pricing.advance_basis || 'net'}
              onChange={(v) => setSel({ advance_basis: v })}
              options={[
                { value: 'net', label: t('net') },
                { value: 'total', label: t('gross') },
              ]}
            />
          </Field>
        </div>
      </div>
    </div>
  )
}
