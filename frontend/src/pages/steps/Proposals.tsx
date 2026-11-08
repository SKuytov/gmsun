import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Clock, Coins, Gem, RefreshCw, Scale, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Segmented, Spinner, Toggle, Warn, cx, useToast } from '@/components/ui'
import { errMsg, post } from '@/lib/api'
import { fmtMoney, fmtNum, useT, type Key } from '@/lib/i18n'
import type { Project, ProposalScope, ProposalVariant, ProposalsResult, Selections, Strategy } from '@/lib/types'
import { TierBadge } from '../Catalog'
import type { StepCtx } from '../Project'

const ICONS: Record<Strategy, typeof Coins> = { economy: Coins, balanced: Scale, premium: Gem, fastest: Clock }
const ORDER: Strategy[] = ['economy', 'balanced', 'premium', 'fastest']

/** Automatic proposals: four complete, costed configurations the user can compare and apply with one click. */
export function Proposals({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { project: p, sel, setSel } = ctx
  const [res, setRes] = useState<ProposalsResult | null>(null)
  const [scope, setScope] = useState<ProposalScope>('auto')
  const gen = useMutation({
    mutationFn: (sc: ProposalScope) => post<ProposalsResult>(`/api/projects/${p.id}/proposals`, { selections: sel, scope: sc }),
    onSuccess: setRes,
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const layoutCount = p.layouts.reduce((s, l) => s + (l.summary?.count || 0), 0)
  const changeScope = (sc: ProposalScope) => {
    setScope(sc)
    gen.mutate(sc)
  }
  const applyServer = useMutation({
    mutationFn: (v: ProposalVariant) => post<Project>(`/api/projects/${p.id}/proposals/apply`, { selections: v.selections, strategy: v.strategy }),
    onSuccess: (proj) => {
      qc.setQueryData(['project', proj.id], proj)
      qc.invalidateQueries({ queryKey: ['project', proj.id] })
      qc.invalidateQueries({ queryKey: ['quotes', proj.id] })
      ctx.replaceSel((proj.params?.selections as Selections) || {})
      toast.push(t('proposals_applied'), 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const apply = (v: ProposalVariant) => {
    if (v.selections.panel_fit) {
      applyServer.mutate(v) // a different module / count than the drawn layout → the server re-places the modules
      return
    }
    setSel({ ...v.selections, strategy: v.strategy })
    toast.push(t('proposals_applied'), 'ok')
  }
  const variants = res ? ORDER.map((s) => res.variants.find((v) => v.strategy === s)).filter((v): v is ProposalVariant => !!v) : []
  const cheapest = variants.length ? Math.min(...variants.map((v) => v.total)) : 0
  const fastest = variants.length ? Math.min(...variants.map((v) => v.lead_time_days)) : 0
  const isCurrent = (v: ProposalVariant) =>
    sel.panel_item_id === v.selections.panel_item_id && sel.inverter_item_id === v.selections.inverter_item_id && (sel.battery_item_id || null) === (v.selections.battery_item_id || null) && (sel.battery_qty || 0) === (v.selections.battery_qty || 0) && (sel.panel_qty || 0) === (v.selections.panel_qty || 0) && (sel.inverter_qty || 1) === (v.selections.inverter_qty || 1) && (sel.panel_limit || 0) === (v.selections.panel_limit || 0)

  return (
    <div className="card p-4" data-testid="proposals-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-sun-ink" /> {t('proposals_title')}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-ink-2">{t('proposals_hint')}</p>
          {res && (
            <p className="mt-1 text-xs text-ink-3">
              {t('proposals_target')}: <span className="num font-medium text-ink-2">{fmtNum(res.target_kwp, 2)} kWp</span> ({t(`proposals_basis_${res.target_basis}` as Key)})
              {res.target_kwh > 0 && (
                <>
                  {' '}
                  · {t('battery')}: <span className="num font-medium text-ink-2">{fmtNum(res.target_kwh, 1)} kWh</span>
                </>
              )}
              {res.roof_kwp > 0 && res.demand_kwp > 0 && (
                <>
                  {' '}
                  · {t('proposals_roof')}: <span className="num font-medium text-ink-2">{fmtNum(res.roof_kwp, 2)} kWp</span> ({res.roof_panel_qty} {t('modules_short')}) · {t('proposals_demand')}:{' '}
                  <span className="num font-medium text-ink-2">{fmtNum(res.demand_kwp, 2)} kWp</span> ({t(`proposals_basis_${res.demand_basis}` as Key)})
                </>
              )}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {layoutCount > 0 && (
            <div data-testid="proposals-scope">
              <Segmented<ProposalScope>
                size="sm"
                value={scope}
                onChange={changeScope}
                options={[
                  { value: 'auto', label: t('scope_auto') },
                  { value: 'target', label: t('scope_target') },
                  { value: 'roof', label: `${t('scope_roof')}${res?.roof_kwp ? ` (${fmtNum(res.roof_kwp, 1)} kWp)` : ''}` },
                ]}
              />
            </div>
          )}
          {layoutCount > 0 && (
            <span title={t('panel_auto_hint')} data-testid="proposals-panel-auto">
              <Toggle checked={sel.panel_auto !== false} onChange={(v) => setSel({ panel_auto: v })} label={t('panel_auto')} />
            </span>
          )}
          <button type="button" className={cx(res ? 'btn-ghost' : 'btn-primary')} onClick={() => gen.mutate(scope)} disabled={gen.isPending} data-testid="button-proposals">
            {gen.isPending ? <Spinner /> : <RefreshCw className="h-4 w-4" />} {res ? t('proposals_regenerate') : t('proposals_generate')}
          </button>
        </div>
      </div>
      {res && res.notes.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5" data-testid="proposals-notes">
          {res.notes.map((n) => (
            <Warn key={n}>{n}</Warn>
          ))}
        </div>
      )}

      {res && variants.length === 0 && <Warn>{lang === 'bg' ? 'Няма подходящи комбинации в каталога за тези параметри (проверете цени и характеристики).' : 'No suitable combinations in the catalog for these parameters (check prices and specs).'}</Warn>}

      {variants.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-4">
          {variants.map((v) => {
            const Icon = ICONS[v.strategy]
            const current = isCurrent(v)
            return (
              <div key={v.strategy} className={cx('flex flex-col rounded-lg border p-3', current ? 'border-sun bg-sun-soft/40' : 'border-line/20 bg-surface')} data-testid={`proposal-${v.strategy}`}>
                <div className="flex items-center gap-2 font-semibold">
                  <Icon className="h-4 w-4 shrink-0 text-ink-2" /> <span className="truncate">{lang === 'bg' ? v.label_bg : v.label_en}</span>
                </div>
                {(v.total === cheapest || v.lead_time_days === fastest) && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {v.total === cheapest && <span className="rounded bg-ok/15 px-1.5 py-0.5 text-[11px] font-medium text-ok">{t('proposals_cheapest')}</span>}
                    {v.lead_time_days === fastest && <span className="rounded bg-line/20 px-1.5 py-0.5 text-[11px] font-medium text-ink-2">{t('proposals_fastest_badge')}</span>}
                  </div>
                )}
                {v.same_as && (
                  <p className="mt-1 text-xs text-ink-3">
                    {t('proposals_same_as')} „{t(`strategy_${v.same_as}` as Key)}“
                  </p>
                )}
                <div className="mt-3 num whitespace-nowrap text-2xl font-semibold leading-tight">
                  {fmtMoney(v.total)} <span className="text-sm font-medium text-ink-3">EUR</span>
                </div>
                <div className="num text-xs text-ink-3">
                  {t('gross')} · {t('net')} {fmtMoney(v.subtotal)}
                  {v.delta_total > 0 && <span className="ml-1 text-warn">(+{fmtMoney(v.delta_total)})</span>}
                </div>
                <div className="mt-2 grid grid-cols-3 gap-1 text-center text-xs">
                  <div className="rounded bg-surface-2 p-1.5" title={v.roof_panel_qty ? `${t('proposals_roof')}: ${v.roof_panel_qty} ${t('modules_short')}` : undefined}>
                    <div className="num font-semibold">{fmtNum(v.kwp, 2)}</div>
                    <div className="text-ink-3">
                      kWp · {v.panel_qty}
                      {v.roof_panel_qty ? `/${v.roof_panel_qty}` : ''}
                    </div>
                  </div>
                  <div className="rounded bg-surface-2 p-1.5">
                    <div className="num font-semibold">{v.ac_kw ? fmtNum(v.ac_kw, 1) : '—'}</div>
                    <div className="text-ink-3">kW AC{v.inverter_qty > 1 ? ` · ${v.inverter_qty}×` : ''}</div>
                  </div>
                  <div className="rounded bg-surface-2 p-1.5" title={v.lead_bottleneck ? `${t('bottleneck')}: ${v.lead_bottleneck}` : undefined}>
                    <div className="num font-semibold">{v.lead_time_days}</div>
                    <div className="text-ink-3">{lang === 'bg' ? 'раб. дни' : 'wd'}</div>
                  </div>
                </div>
                <ul className="mt-3 flex flex-1 flex-col gap-1.5 text-xs">
                  {v.key_items.map((k) => (
                    <li key={k.role} className="flex items-start gap-1.5">
                      <span className="w-[4.5rem] shrink-0 text-ink-3">{k.label}</span>
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 font-medium" title={k.name}>
                          {k.qty > 0 && k.role !== 'mounting' ? `${k.qty} × ` : ''}
                          {k.name}
                        </span>
                        <span className="mt-0.5 flex flex-wrap items-center gap-1 text-ink-3">
                          {k.tier && <TierBadge tier={k.tier} manual />}
                          {k.lead_time_days != null && (
                            <span>
                              {k.lead_time_days} {lang === 'bg' ? 'дни' : 'd'}
                            </span>
                          )}
                          {k.supplier && <span>· {k.supplier}</span>}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="mt-2 text-xs text-ink-3">
                  ≈ {fmtNum(v.yield_kwh, 0)} {t('yield_year')}
                  {v.execution_days ? ` · ${v.execution_days} ${lang === 'bg' ? 'дни монтаж' : 'install days'}` : ''}
                  {' · '}
                  {t('margin')}: <span className="num">{fmtMoney(v.margin)}</span>
                </div>
                {v.missing_price.length > 0 && (
                  <p className="mt-1 text-xs text-warn">
                    {t('unpriced')}: {v.missing_price.slice(0, 2).join(', ')}
                    {v.missing_price.length > 2 ? '…' : ''}
                  </p>
                )}
                <button type="button" className={cx('mt-3 w-full', current ? 'btn-ghost' : 'btn-primary')} onClick={() => apply(v)} disabled={current} data-testid={`button-apply-${v.strategy}`}>
                  {current ? (
                    <>
                      <Check className="h-4 w-4" /> {t('proposals_current')}
                    </>
                  ) : (
                    t('proposals_apply')
                  )}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
