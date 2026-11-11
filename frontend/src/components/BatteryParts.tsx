import { useQuery } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { Field, NumInput, Segmented, Select, Warn, cx } from '@/components/ui'
import { post } from '@/lib/api'
import { useT } from '@/lib/i18n'
import type { BatteryPartMode, BatteryPartOption, BatteryPartSel, BatteryPartsInfo, Selections } from '@/lib/types'

type Kind = 'bms' | 'rack'

/**
 * BMS / control box and rack / cabinet as two independent selections.
 * Each one: automatic (engineering choice), manual (pick catalog items + qty) or none.
 * Only items of the curated catalog are offered; items of another battery family are shown but disabled.
 */
export function BatteryParts({ sel, setSel }: { sel: Selections; setSel: (patch: Partial<Selections>) => void }) {
  const { lang } = useT()
  const bg = lang === 'bg'
  const body = {
    selections: {
      battery_item_id: sel.battery_item_id,
      battery_qty: sel.battery_qty,
      inverter_item_id: sel.inverter_item_id,
      inverter_qty: sel.inverter_qty,
      battery_bms: sel.battery_bms,
      battery_rack: sel.battery_rack,
      battery_accessories: sel.battery_accessories,
    },
  }
  const q = useQuery({
    queryKey: ['battery-parts', JSON.stringify(body)],
    queryFn: () => post<BatteryPartsInfo>('/api/sizing/battery-parts', body),
    enabled: !!sel.battery_item_id,
    placeholderData: (prev) => prev,
  })
  const info = q.data
  if (!sel.battery_item_id || !info) return null

  const cfgOf = (k: Kind): BatteryPartSel => (k === 'bms' ? sel.battery_bms : sel.battery_rack) || info.config[k]
  const put = (k: Kind, v: BatteryPartSel) => setSel(k === 'bms' ? { battery_bms: v } : { battery_rack: v })

  const setMode = (k: Kind, mode: BatteryPartMode) => {
    const cur = cfgOf(k)
    if (mode === 'manual' && cur.items.length === 0) {
      // start from the engineering choice, else the first compatible catalog item
      const fromAuto = info.auto[k].map((a) => ({ item_id: a.item_id, qty: a.qty }))
      const first = info.options[k].find((o) => o.compatible)
      put(k, { mode, items: fromAuto.length ? fromAuto : first ? [{ item_id: first.item_id, qty: 1 }] : [] })
    } else put(k, { ...cur, mode })
  }

  const label = (o: BatteryPartOption) => {
    const extra = o.capacity ? ` · ${bg ? 'до' : 'up to'} ${o.capacity} ${bg ? 'модула' : 'modules'}` : o.max_series ? ` · ${bg ? 'до' : 'up to'} ${o.max_series} ${bg ? 'в серия' : 'in series'}` : ''
    return `${o.name}${extra}${o.compatible ? '' : bg ? ' — за друга серия' : ' — other series'}`
  }

  const block = (k: Kind, title: string, autoEmpty: string) => {
    const cfg = cfgOf(k)
    const opts = info.options[k]
    return (
      <div className="rounded border border-line/15 p-3" data-testid={`battery-part-${k}`}>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm font-semibold">{title}</span>
          <Segmented<BatteryPartMode>
            size="sm"
            value={cfg.mode}
            onChange={(m) => setMode(k, m)}
            options={[
              { value: 'auto', label: bg ? 'Автоматично' : 'Automatic' },
              { value: 'manual', label: bg ? 'Ръчно' : 'Manual' },
              { value: 'none', label: bg ? 'Без' : 'None' },
            ]}
          />
        </div>
        {cfg.mode === 'auto' && (
          <ul className="flex flex-col gap-0.5 text-sm">
            {info.auto[k].length === 0 && <li className="text-ink-3">{autoEmpty}</li>}
            {info.auto[k].map((a) => (
              <li key={a.item_id}>
                <span className="num font-semibold">{a.qty} ×</span> {a.name} <span className="text-xs text-ink-3">· {a.why}</span>
              </li>
            ))}
          </ul>
        )}
        {cfg.mode === 'manual' && (
          <div className="flex flex-col gap-2">
            {opts.length === 0 && <span className="text-sm text-ink-3">{bg ? 'Няма такива артикули в каталога (категория „Аксесоари за батерии“).' : 'No such items in the catalog (category “Battery accessories”).'}</span>}
            {cfg.items.map((row, i) => (
              <div key={i} className="flex items-center gap-2">
                <Select
                  className="min-w-0 flex-1"
                  value={row.item_id}
                  onChange={(e) => put(k, { ...cfg, items: cfg.items.map((x, j) => (j === i ? { ...x, item_id: Number(e.target.value) } : x)) })}
                  data-testid={`select-battery-${k}-${i}`}
                >
                  {opts.map((o) => (
                    <option key={o.item_id} value={o.item_id} disabled={!o.compatible}>
                      {label(o)}
                    </option>
                  ))}
                </Select>
                <NumInput
                  className="input-sm w-20"
                  value={row.qty}
                  min={0}
                  onChange={(v) => put(k, { ...cfg, items: cfg.items.map((x, j) => (j === i ? { ...x, qty: Math.max(0, Math.round(v)) } : x)) })}
                  data-testid={`input-battery-${k}-qty-${i}`}
                />
                <button type="button" className="btn-ghost btn-sm" aria-label={bg ? 'Премахни' : 'Remove'} onClick={() => put(k, { ...cfg, items: cfg.items.filter((_x, j) => j !== i) })}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            {opts.some((o) => o.compatible) && (
              <button
                type="button"
                className="btn-ghost btn-sm self-start"
                onClick={() => {
                  const used = new Set(cfg.items.map((x) => x.item_id))
                  const next = opts.find((o) => o.compatible && !used.has(o.item_id)) || opts.find((o) => o.compatible)!
                  put(k, { ...cfg, items: [...cfg.items, { item_id: next.item_id, qty: 1 }] })
                }}
                data-testid={`button-add-battery-${k}`}
              >
                <Plus className="h-4 w-4" /> {bg ? 'Добави' : 'Add'}
              </button>
            )}
          </div>
        )}
        {cfg.mode === 'none' && <span className="text-sm text-ink-3">{bg ? 'Не се включва в офертата.' : 'Not included in the quote.'}</span>}
      </div>
    )
  }

  const others = sel.battery_accessories || []
  const otherOpts = info.options.other
  return (
    <Field label={bg ? 'Аксесоари за батерията' : 'Battery accessories'} className="col-span-2">
      <div className="flex flex-col gap-2">
        {block('bms', bg ? 'BMS / контролна кутия' : 'BMS / control box', info.hv ? (bg ? 'Няма подходящ BMS в каталога.' : 'No matching BMS in the catalog.') : bg ? 'Вграден в батерията (LV) — не е нужен отделен.' : 'Built into the battery (LV) — none needed.')}
        {block('rack', bg ? 'Стелаж / кутия (rack)' : 'Rack / cabinet', info.hv ? (bg ? 'Няма подходящ стелаж в каталога.' : 'No matching rack in the catalog.') : bg ? 'Не е нужен за тази батерия (монтаж на стена / под).' : 'Not needed for this battery (wall / floor mount).')}
        {info.hv && info.clusters.length > 0 && (
          <span className="text-xs text-ink-3">
            {bg ? 'Конфигурация' : 'Configuration'}: {info.clusters.join(' + ')} {bg ? 'модула' : 'modules'} · {info.clusters.length} {bg ? (info.clusters.length === 1 ? 'клъстер (1 BMS)' : `клъстера (${info.clusters.length} BMS)`) : `cluster(s)`}
          </span>
        )}
        {(others.length > 0 || otherOpts.length > 0) && (
          <div className="rounded border border-line/15 p-3">
            <div className="mb-2 text-sm font-semibold">{bg ? 'Други аксесоари' : 'Other accessories'}</div>
            <div className="flex flex-col gap-2">
              {others.map((row, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Select className="min-w-0 flex-1" value={row.item_id} onChange={(e) => setSel({ battery_accessories: others.map((x, j) => (j === i ? { ...x, item_id: Number(e.target.value) } : x)) })}>
                    {!otherOpts.some((o) => o.item_id === row.item_id) && <option value={row.item_id}>{bg ? 'Артикул' : 'Item'} #{row.item_id}</option>}
                    {otherOpts.map((o) => (
                      <option key={o.item_id} value={o.item_id} disabled={!o.compatible}>
                        {label(o)}
                      </option>
                    ))}
                  </Select>
                  <NumInput className="input-sm w-20" value={row.qty} min={0} onChange={(v) => setSel({ battery_accessories: others.map((x, j) => (j === i ? { ...x, qty: v } : x)) })} />
                  <button type="button" className="btn-ghost btn-sm" aria-label={bg ? 'Премахни' : 'Remove'} onClick={() => setSel({ battery_accessories: others.filter((_x, j) => j !== i) })}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
              {otherOpts.some((o) => o.compatible) && (
                <button type="button" className="btn-ghost btn-sm self-start" onClick={() => setSel({ battery_accessories: [...others, { item_id: otherOpts.find((o) => o.compatible)!.item_id, qty: 1 }] })}>
                  <Plus className="h-4 w-4" /> {bg ? 'Добави аксесоар' : 'Add accessory'}
                </button>
              )}
              <span className="text-xs text-ink-3">{bg ? 'Батерийните кабели, обувките и CAN кабелът се оразмеряват автоматично в стъпка „Материали“.' : 'Battery cables, lugs and the CAN cable are sized automatically in the Materials step.'}</span>
            </div>
          </div>
        )}
        {info.warnings.length > 0 && (
          <Warn>
            <ul className="flex flex-col gap-0.5">
              {info.warnings.map((w, i) => (
                <li key={i} className={cx(w.startsWith('НЕСЪВМЕСТИМО') && 'text-bad')}>{w}</li>
              ))}
            </ul>
          </Warn>
        )}
      </div>
    </Field>
  )
}
