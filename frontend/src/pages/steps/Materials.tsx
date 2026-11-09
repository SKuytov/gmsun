import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Field, Input, NumInput, Segmented, Select, Toggle } from '@/components/ui'
import { post } from '@/lib/api'
import { fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { CatalogItem, Design, Selections } from '@/lib/types'
import type { StepCtx } from '../Project'
import { MountingSystemCard } from '@/components/MountingSystem'

function useDebounced<T>(v: T, ms = 500) {
  const [d, setD] = useState(v)
  useEffect(() => {
    const h = setTimeout(() => setD(v), ms)
    return () => clearTimeout(h)
  }, [v, ms])
  return d
}

const SECTION_ORDER = ['electrical', 'inverter', 'construction', 'modules']

function DesignPanel({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const { sel, project: p } = ctx
  const key = useDebounced(JSON.stringify([sel, p.params, p.phase, p.roof_type]))
  const q = useQuery({
    queryKey: ['design', p.id, key],
    queryFn: () => post<Design>(`/api/sizing/projects/${p.id}/design`, { selections: sel }),
    placeholderData: (prev) => prev,
  })
  const d = q.data
  if (!d) return <p className="text-sm text-ink-3">{q.isLoading ? '…' : '—'}</p>
  const n = (v: unknown, digits = 0) => (typeof v === 'number' ? fmtNum(v, digits) : String(v ?? '—'))
  const Row = ({ k, v }: { k: string; v: unknown }) => (
    <div className="flex justify-between gap-3 text-sm">
      <span className="text-ink-3">{k}</span>
      <span className="num text-right">{String(v ?? '—')}</span>
    </div>
  )
  const covered = d.roles.filter((r) => r.status === 'covered')
  const notQuoted = d.roles.filter((r) => !r.item_id && r.status !== 'covered')
  const sorted = [...d.roles].sort((a, b) => SECTION_ORDER.indexOf(a.section) - SECTION_ORDER.indexOf(b.section))
  const warnings = Array.from(new Set([...(d.warnings || []), ...(d.strings?.warnings || [])]))
  return (
    <div className="flex flex-col gap-3">
      {warnings.length > 0 && (
        <ul className="rounded-md border border-warn/40 bg-warn/10 p-2 text-sm">
          {warnings.map((w, i) => (
            <li key={i} className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" /> {w}
            </li>
          ))}
        </ul>
      )}
      {d.strings?.checks?.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {d.strings.checks.map((c, i) => (
            <li key={i} className="flex gap-2">
              {c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />} {c.text}
            </li>
          ))}
        </ul>
      )}
      {d.strings?.strings?.length > 0 && (
        <div className="overflow-x-auto">
          <table className="tbl text-xs">
            <thead>
              <tr>
                <th>{t('strings')}</th>
                {(d.inverters || 1) > 1 && <th className="text-center">{lang === 'bg' ? 'Инв.' : 'Inv.'}</th>}
                <th>{lang === 'bg' ? 'Равнина' : 'Plane'}</th>
                <th className="text-right">{t('modules')}</th>
                <th className="text-right">Voc (min T)</th>
                <th className="text-right">Vmp (STC)</th>
                <th className="text-center">MPPT / {lang === 'bg' ? 'вход' : 'input'}</th>
                <th className="text-right">ΔU %</th>
              </tr>
            </thead>
            <tbody>
              {d.strings.strings.map((s) => (
                <tr key={s.id}>
                  <td className="font-medium">{s.id}</td>
                  {(d.inverters || 1) > 1 && <td className="text-center">{s.inverter}</td>}
                  <td>{s.plane}</td>
                  <td className="num text-right">{s.modules}</td>
                  <td className="num text-right">{n(s.voc_cold_v)} V</td>
                  <td className="num text-right">{n(s.vmp_stc_v)} V</td>
                  <td className="text-center">
                    {s.mppt} / {s.input}
                  </td>
                  <td className="num text-right">{n(s.vdrop_pct, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-md bg-surface-2 p-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">{t('design_dc')}</h3>
          <Row k={lang === 'bg' ? 'Соларен кабел' : 'PV cable'} v={`${n(d.dc.cable_mm2)} mm² · ${n(d.dc.red_m)} / ${n(d.dc.black_m)} m`} />
          <Row k={lang === 'bg' ? 'Изчислителен ток' : 'Design current'} v={`${n(d.dc.design_current_a, 1)} A`} />
          <Row k={lang === 'bg' ? 'Макс. пад' : 'Max. drop'} v={`${n(d.dc.vdrop_worst_pct, 2)} %`} />
          <Row k={t('dc_box')} v={d.dc.box ? t('yes') : t('no')} />
          <Row k="MC4" v={`${n(d.dc.mc4_pairs)} ${lang === 'bg' ? 'компл.' : 'pairs'}`} />
        </div>
        <div className="rounded-md bg-surface-2 p-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">{t('design_ac')}</h3>
          {d.ac.combiner ? (
            <>
              <Row k={lang === 'bg' ? 'Инвертори' : 'Inverters'} v={`${n(d.ac.inverters)} × ${n(d.ac.i_max_a, 1)} A = ${n(d.ac.i_total_a, 1)} A · ${n(d.ac.p_total_kw, 1)} kW`} />
              <Row k={lang === 'bg' ? 'Защита на инвертор' : 'Per-inverter protection'} v={`${d.ac.breaker_poles ?? ''} ${n(d.ac.breaker_a)} A + RCD ${n(d.ac.rcd_a)} A / ${n(d.ac.rcd_ma)} mA`} />
              <Row k={lang === 'bg' ? 'Кабел → табло AC' : 'Cable → AC combiner'} v={`${n(d.ac.cores)}×${n(d.ac.cable_mm2)} mm² · ${n(d.ac.cable_m)} m`} />
              <Row k={lang === 'bg' ? 'Главен прекъсвач' : 'Main breaker'} v={`${d.ac.breaker_poles ?? ''} ${n(d.ac.main_breaker_a)} A`} />
              <Row k={lang === 'bg' ? 'Кабел табло AC → ГРТ' : 'Combiner → main board'} v={`${n(d.ac.cores)}×${n(d.ac.main_cable_mm2)} mm² · ${n(d.ac.main_cable_m)} m · ΔU ${n(d.ac.main_vdrop_pct, 2)} %`} />
            </>
          ) : (
            <>
              <Row k={lang === 'bg' ? 'Макс. ток' : 'Max. current'} v={`${n(d.ac.i_max_a, 1)} A`} />
              <Row k={lang === 'bg' ? 'Прекъсвач' : 'Breaker'} v={`${d.ac.breaker_poles ?? ''} ${n(d.ac.breaker_a)} A`} />
              <Row k={lang === 'bg' ? 'Дефектнотокова' : 'RCD'} v={d.ac.rcd_a ? `${n(d.ac.rcd_a)} A / ${n(d.ac.rcd_ma)} mA` : '—'} />
              <Row k={lang === 'bg' ? 'Кабел' : 'Cable'} v={d.ac.cable_mm2 ? `${n(d.ac.cores)}×${n(d.ac.cable_mm2)} mm² · ${n(d.ac.cable_m)} m` : '—'} />
              <Row k={lang === 'bg' ? 'Пад' : 'Drop'} v={`${n(d.ac.vdrop_pct, 2)} %`} />
            </>
          )}
        </div>
        <div className="rounded-md bg-surface-2 p-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">{t('design_battery')}</h3>
          <Row k={lang === 'bg' ? 'Прекъсвач' : 'Breaker'} v={d.battery.breaker_a ? `${n(d.battery.breaker_a)} A` : '—'} />
          <Row k={lang === 'bg' ? 'Кабел' : 'Cable'} v={d.battery.cable_mm2 ? `${n(d.battery.cable_mm2)} mm² · ${n(d.battery.cable_m)} m` : '—'} />
          <Row k={lang === 'bg' ? 'Входове' : 'Inputs'} v={n(d.battery.inputs)} />
        </div>
        <div className="rounded-md bg-surface-2 p-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-3">{t('design_grounding')}</h3>
          <Row k="PE" v={d.grounding.pe_mm2 ? `${n(d.grounding.pe_mm2)} mm² · ${n(d.grounding.pe_m)} m` : '—'} />
          <Row k={lang === 'bg' ? 'Изравняване' : 'Bonding'} v={`${n(d.grounding.bonding_mm2)} mm² · ${n(d.grounding.bonding_m)} m`} />
          <Row k={lang === 'bg' ? 'Клеми' : 'Clamps'} v={n(d.grounding.bonding_clamps)} />
          <Row k={lang === 'bg' ? 'Връзки / тръба' : 'Ties / conduit'} v={`${n(d.management.ties)} / ${n(Number(d.management.conduit_dc_m || 0) + Number(d.management.conduit_ac_m || 0))} m`} />
        </div>
      </div>
      <details className="rounded-md border border-line/15">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
          {t('design_bom')} ({d.roles.length})
          {covered.length > 0 && <span className="ml-2 text-ok">· {covered.length} {lang === 'bg' ? 'в таблото' : 'in the board'}</span>}
          {notQuoted.length > 0 && <span className="ml-2 text-ink-3">· {notQuoted.length} {lang === 'bg' ? 'само за справка (без артикул)' : 'reference only (no article)'}</span>}
        </summary>
        <p className="px-3 pb-2 text-xs text-ink-3">
          {lang === 'bg'
            ? `Инженерният списък показва всичко нужно за монтажа. В офертата влизат само артикулите от каталога; защитите и кутиите са включени в оборудваното AC/DC табло${d.switchboard ? ` („${d.switchboard.name}“ × ${d.switchboard.qty})` : ''}, а позициите без артикул са само за справка.`
            : `The engineering list shows everything the installation needs. Only catalog articles are quoted; protections and enclosures are part of the equipped AC/DC board${d.switchboard ? ` ("${d.switchboard.name}" × ${d.switchboard.qty})` : ''}, rows without an article are for reference only.`}
        </p>
        <div className="max-h-80 overflow-auto">
          <table className="tbl text-xs">
            <tbody>
              {sorted.map((r, i) => (
                <tr key={i} className={r.item_id ? '' : 'text-ink-3'} data-testid={`design-role-${r.role}`}>
                  <td className="text-ink-3">{r.section}</td>
                  <td>{r.role === 'pv_cable' ? r.name : r.item_name || r.name}</td>
                  <td className="num whitespace-nowrap text-right">
                    {fmtNum(r.qty, 0)} {r.unit}
                  </td>
                  <td className="num whitespace-nowrap text-right">
                    {r.unit_price != null ? fmtMoney(r.unit_price) : r.status === 'covered' ? (lang === 'bg' ? 'в таблото' : 'in board') : lang === 'bg' ? 'не се офертира' : 'not quoted'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="text-xs text-ink-3">
        {lang === 'bg' ? 'Резерв' : 'Margins'}: {lang === 'bg' ? 'кабели' : 'cables'} {n(d.margins.cable_pct)} % · {lang === 'bg' ? 'крепежи' : 'fasteners'} {n(d.margins.fastener_pct)} % · {lang === 'bg' ? 'модули' : 'modules'} {n(d.margins.module_spare_pct)} %
      </p>
    </div>
  )
}

function ItemSelect({ items, value, onChange, allowNone = true, label, testId, noneLabel }: { items: CatalogItem[]; value: number | null | undefined; onChange: (id: number | null) => void; allowNone?: boolean; label: string; testId?: string; noneLabel?: string }) {
  const { t } = useT()
  return (
    <Field label={label}>
      <Select value={value ?? ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} data-testid={testId}>
        {allowNone && <option value="">{noneLabel ?? t('none')}</option>}
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
  const selInv = items.find((i) => i.id === sel.inverter_item_id)
  const boardPhase = Number(selInv?.specs?.phases || p.phase || 3)
  const sb = by('switchboard').filter((x) => !x.specs.phases || Number(x.specs.phases) === boardPhase)
  const invQtyM = Math.max(1, Number(sel.inverter_qty || 1))
  const roof = ctx.roofTypes.find((r) => r.code === p.roof_type)
  const electrical = by('electrical')
  const mc4Items = items.filter((i) => i.active && /mc4/i.test(i.name))
  const autoLabel = lang === 'bg' ? '— автоматично по проектирането —' : '— automatic from the design —'
  const mounting = by('mounting')
  const extras = sel.extra_items || []
  const el = sel.electrical_items || []
  const params = (p.params || {}) as Record<string, unknown>
  const num = (v: unknown) => (typeof v === 'number' ? v : undefined)
  const setParam = (k: string, v: number) => ctx.update({ params: { ...params, [k]: v } })
  const autoHint = lang === 'bg' ? 'празно = авто' : 'empty = auto'

  // Smart defaults: pre-select the first matching catalog item and estimate cable lengths once.
  // Explicit "none" is stored as null and is never overridden.
  // The AC/DC board follows the inverter: empty = automatic by inverter phases (1 board per inverter). A board picked
  // for the wrong number of phases (e.g. after switching the inverter) is reset to automatic.
  useEffect(() => {
    const cur = items.find((i) => i.id === sel.switchboard_item_id)
    if (cur && cur.specs.phases && Number(cur.specs.phases) !== boardPhase) setSel({ switchboard_item_id: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardPhase, sel.switchboard_item_id])

  const setExtra = (i: number, patch: Partial<NonNullable<Selections['extra_items']>[number]>) => setSel({ extra_items: extras.map((x, j) => (j === i ? { ...x, ...patch } : x)) })

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="card flex flex-col gap-3 p-4">
        <h2>{t('section_electrical')}</h2>
        <ItemSelect
          label={`${t('switchboard')} (${t(boardPhase === 1 ? 'phase_1' : 'phase_3')}${invQtyM > 1 ? ` · ${invQtyM} ${lang === 'bg' ? 'бр. — по едно на инвертор' : 'pcs — one per inverter'}` : ''})`}
          items={sb.length ? sb : by('switchboard')}
          value={sel.switchboard_item_id}
          onChange={(v) => setSel({ switchboard_item_id: v })}
          testId="select-switchboard"
          noneLabel={lang === 'bg' ? '— автоматично по инвертора —' : '— automatic by inverter —'}
        />
        <ItemSelect label={t('solar_cable')} items={by('solar_cable')} value={sel.solar_cable_item_id} onChange={(v) => setSel({ solar_cable_item_id: v })} testId="select-solar-cable" noneLabel={autoLabel} />
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('red_m')} hint={autoHint}>
            <NumInput value={sel.solar_cable_red_m ?? null} min={0} placeholder={t('auto')} onChange={(v) => setSel({ solar_cable_red_m: v > 0 ? v : null })} data-testid="input-red-m" />
          </Field>
          <Field label={t('black_m')} hint={autoHint}>
            <NumInput value={sel.solar_cable_black_m ?? null} min={0} placeholder={t('auto')} onChange={(v) => setSel({ solar_cable_black_m: v > 0 ? v : null })} />
          </Field>
        </div>
        {mc4Items.length > 0 && <div className="grid grid-cols-[1fr_7rem] gap-3">
          <ItemSelect label={t('mc4')} items={mc4Items} value={sel.mc4_item_id} onChange={(v) => setSel({ mc4_item_id: v })} noneLabel={autoLabel} />
          <Field label={t('qty')} hint={autoHint}>
            <NumInput value={sel.mc4_qty ?? null} min={0} placeholder={t('auto')} onChange={(v) => setSel({ mc4_qty: v > 0 ? v : null })} />
          </Field>
        </div>}
        {by('power_cable').length > 0 && <div className="grid grid-cols-[1fr_7rem] gap-3">
          <ItemSelect label={t('power_cable')} items={by('power_cable')} value={sel.power_cable_item_id} onChange={(v) => setSel({ power_cable_item_id: v })} testId="select-power-cable" noneLabel={autoLabel} />
          <Field label={t('length_m')} hint={autoHint}>
            <NumInput value={sel.power_cable_m ?? null} min={0} placeholder={t('auto')} onChange={(v) => setSel({ power_cable_m: v > 0 ? v : null })} />
          </Field>
        </div>}

        <h2 className="mt-2 text-base">{t('distances')}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label={t('dc_run_m')}>
            <NumInput value={num(params.dc_run_m) ?? ctx.pricing.dc_run_default_m} min={0} onChange={(v) => setParam('dc_run_m', v)} data-testid="input-dc-run" />
          </Field>
          <Field label={t('ac_run_m')}>
            <NumInput value={num(params.ac_run_m) ?? ctx.pricing.ac_run_default_m} min={0} onChange={(v) => setParam('ac_run_m', v)} />
          </Field>
          <Field label={t('battery_run_m')}>
            <NumInput value={num(params.battery_run_m) ?? 2} min={0} onChange={(v) => setParam('battery_run_m', v)} />
          </Field>
          <Field label={t('backup_run_m')}>
            <NumInput value={num(params.backup_run_m) ?? 5} min={0} onChange={(v) => setParam('backup_run_m', v)} />
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t('dc_box')}>
            <Segmented
              size="sm"
              value={sel.dc_box || 'auto'}
              onChange={(v) => setSel({ dc_box: v })}
              options={[
                { value: 'auto', label: t('auto') },
                { value: 'yes', label: t('yes') },
                { value: 'no', label: t('no') },
              ]}
            />
          </Field>
          <Field label={t('metering')}>
            <Segmented
              size="sm"
              value={sel.metering || 'ct'}
              onChange={(v) => setSel({ metering: v })}
              options={[
                { value: 'ct', label: t('metering_ct') },
                { value: 'smart_meter', label: t('metering_smart') },
              ]}
            />
          </Field>
          <Field label={t('design_tmin_c')}>
            <NumInput value={num(params.design_tmin_c) ?? ctx.pricing.design_tmin_c} onChange={(v) => setParam('design_tmin_c', v)} />
          </Field>
          <Field label={t('module_spare_pct')}>
            <NumInput value={sel.module_spare_pct ?? ctx.pricing.module_spare_pct} min={0} max={50} onChange={(v) => setSel({ module_spare_pct: v })} />
          </Field>
        </div>
        <div className="flex flex-col">
          <Toggle checked={!!sel.dc_box_fuses} onChange={(v) => setSel({ dc_box_fuses: v })} label={`${t('dc_box_fuses')} (${lang === 'bg' ? 'авто при необходимост по IEC 62548' : 'auto when required by IEC 62548'})`} disabled={sel.dc_box === 'no'} />
          <Toggle checked={!!sel.backup_output} onChange={(v) => setSel({ backup_output: v })} label={t('backup_output')} />
          <Toggle checked={sel.earth_rod ?? p.roof_type.startsWith('ground')} onChange={(v) => setSel({ earth_rod: v })} label={t('earth_rod')} />
          <Toggle checked={sel.auto_electrical !== false} onChange={(v) => setSel({ auto_electrical: v })} label={t('auto_electrical')} />
        </div>

        {(electrical.length > 0 || el.length > 0) && <>
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
        </>}
      </div>

      <div className="flex flex-col gap-5">
        <div className="card flex flex-col gap-3 p-4" data-testid="design-panel">
          <h2>{t('design_title')}</h2>
          <p className="text-xs text-ink-3">{t('design_hint')}</p>
          <DesignPanel ctx={ctx} />
        </div>

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
              ...(mounting.length > 0 ? [{ value: 'detailed' as const, label: t('mounting_detailed') }] : []),
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
          {sel.mounting_mode !== 'none' && mounting.length > 0 && <MountingSystemCard roofType={p.roof_type} />}
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
  const mode = sel.labor_mode || pricing.labor_mode_default || 'per_inverter_kw'
  const inv = ctx.items.find((i) => i.id === sel.inverter_item_id)
  const invQty = Math.max(1, Number(sel.inverter_qty || 1))
  const invKw = Number(inv?.specs?.ac_power_kw || 0) * invQty
  const rateDefault = Number(pricing.labor_eur_per_inverter_kw ?? 0)
  const rate = sel.labor_eur_per_kw ?? rateDefault
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
          onChange={(v) => setSel({ labor_mode: v, labor_auto: false })}
          options={[
            { value: 'per_inverter_kw', label: t('labor_per_inv_kw') },
            { value: 'matrix', label: t('labor_matrix') },
            { value: 'per_w', label: t('labor_per_w') },
            { value: 'manual', label: t('labor_manual') },
          ]}
        />
        {mode === 'per_inverter_kw' && (
          <div className="flex flex-col gap-3" data-testid="labor-per-inverter-kw">
            <div className="grid grid-cols-2 gap-3">
              <Field label={`${t('labor_rate_kw')} (EUR/kW)`} hint={lang === 'bg' ? `По подразбиране от Настройки: ${fmtNum(rateDefault, 2)} €/kW` : `Default from Settings: ${fmtNum(rateDefault, 2)} €/kW`}>
                <NumInput
                  value={rate}
                  min={0}
                  step={1}
                  onChange={(v) => setSel({ labor_eur_per_kw: v })}
                  data-testid="input-labor-rate-kw"
                />
              </Field>
              <div className="self-end pb-2 text-sm text-ink-2">
                {inv ? (
                  <>
                    {invQty > 1 ? `${invQty} × ${fmtNum(Number(inv.specs?.ac_power_kw || 0), 0)} kW` : `${fmtNum(invKw, 0)} kW`} × {fmtNum(rate, 2)} ={' '}
                    <span className="num font-semibold" data-testid="text-labor-total">
                      {fmtMoney(invKw * rate)}
                    </span>
                  </>
                ) : (
                  <span className="text-warn">{lang === 'bg' ? 'Изберете инвертор в стъпка „Оборудване“.' : 'Select an inverter in the Equipment step.'}</span>
                )}
              </div>
            </div>
            {sel.labor_eur_per_kw != null && sel.labor_eur_per_kw !== rateDefault && (
              <button type="button" className="btn-quiet btn-sm self-start" onClick={() => setSel({ labor_eur_per_kw: null })} data-testid="button-labor-rate-reset">
                {lang === 'bg' ? 'Върни ставката от Настройки' : 'Use the rate from Settings'}
              </button>
            )}
            <p className="text-xs text-ink-3">
              {lang === 'bg'
                ? `Трудът се изчислява по мощността на инвертора, не на модулите (${fmtNum(ctx.kwp, 2)} kWp). Матрицата дни × хора се използва само за графика на монтажа.`
                : `Labor is based on the inverter power, not the module power (${fmtNum(ctx.kwp, 2)} kWp). The days × workers matrix is only used for the installation schedule.`}
            </p>
          </div>
        )}
        {(mode === 'matrix' || mode === 'per_inverter_kw') && (
          <div className="overflow-x-auto">
            {mode === 'per_inverter_kw' && <div className="mb-1 text-xs font-medium text-ink-2">{lang === 'bg' ? 'График (дни × хора)' : 'Schedule (days × workers)'}</div>}
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
                              onClick={() => setSel({ labor_option_id: o.id, labor_auto: false })}
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
