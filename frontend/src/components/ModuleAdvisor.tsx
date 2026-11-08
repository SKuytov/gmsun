/* Module recommendation: every catalog module laid out on the real planes, ranked per strategy. */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Badge, Segmented, Spinner, cx, useToast } from '@/components/ui'
import { errMsg, post } from '@/lib/api'
import { fmtNum, useT } from '@/lib/i18n'
import type { ModuleCandidate, ModuleRecommendation, Project, ProposalScope, Strategy } from '@/lib/types'

const STRATS: Strategy[] = ['economy', 'balanced', 'premium', 'fastest']

export function ModuleAdvisor({ project, compact = false, onApplied }: { project: Project; compact?: boolean; onApplied?: (p: Project) => void }) {
  const { t, lang } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [strategy, setStrategy] = useState<Strategy>(((project.params?.selections as { strategy?: Strategy } | undefined)?.strategy) || 'balanced')
  const [scope, setScope] = useState<ProposalScope>('auto')
  const [open, setOpen] = useState<number | null>(null)
  const [more, setMore] = useState(false)
  const [res, setRes] = useState<ModuleRecommendation | null>(null)

  const run = useMutation({
    mutationFn: (args: { strategy: Strategy; scope: ProposalScope }) => post<ModuleRecommendation>(`/api/projects/${project.id}/module-recommendations`, { ...args, top: 8 }),
    onSuccess: (r) => {
      setRes(r)
      setOpen(r.candidates[0]?.item_id ?? null)
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const apply = useMutation({
    mutationFn: (c: ModuleCandidate) => post<Project>(`/api/projects/${project.id}/module-recommendations/apply`, { panel_item_id: c.item_id, scope: res?.scope_requested || scope }),
    onSuccess: (p) => {
      qc.setQueryData(['project', p.id], p)
      qc.invalidateQueries({ queryKey: ['project', p.id] })
      qc.invalidateQueries({ queryKey: ['quotes', p.id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.push(t('advisor_applied'), 'ok')
      onApplied?.(p)
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })

  const go = (s = strategy, sc = scope) => run.mutate({ strategy: s, scope: sc })
  const shown = res ? (more ? res.candidates : res.candidates.slice(0, compact ? 3 : 5)) : []
  const badgeLabel: Record<string, string> = { cost: t('advisor_badge_cost'), kwp: t('advisor_badge_kwp'), lead: t('advisor_badge_lead'), eff: t('advisor_badge_eff') }

  return (
    <div className="card flex flex-col gap-3 p-3" data-testid="module-advisor">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="h-4 w-4 text-sun-ink" /> {t('advisor_title')}
          </h3>
          {!compact && <p className="mt-1 text-xs text-ink-3">{t('advisor_hint')}</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          size="sm"
          value={strategy}
          onChange={(v) => {
            setStrategy(v)
            if (res) go(v, scope)
          }}
          options={STRATS.map((s) => ({ value: s, label: t(`strategy_${s}` as 'strategy_economy') }))}
        />
        <Segmented
          size="sm"
          value={scope}
          onChange={(v) => {
            setScope(v)
            if (res) go(strategy, v)
          }}
          options={[
            { value: 'auto', label: t('scope_auto') },
            { value: 'target', label: t('scope_target') },
            { value: 'roof', label: t('scope_roof') },
          ]}
        />
        <button type="button" className={cx('btn-sm ml-auto', res ? 'btn-ghost' : 'btn-primary')} onClick={() => go()} disabled={run.isPending} data-testid="button-advisor-run">
          {run.isPending ? <Spinner /> : <Sparkles className="h-4 w-4" />} {res ? t('proposals_regenerate') : t('advisor_run')}
        </button>
      </div>
      {project.layouts.length === 0 && <p className="text-xs text-warn">{t('advisor_no_layout')}</p>}

      {res && (
        <>
          <p className="text-xs text-ink-3">
            {res.evaluated} {t('advisor_evaluated')} · {t('advisor_target')}: {res.target_kwp ? `${fmtNum(res.target_kwp, 1)} kWp` : '—'} · {res.scope === 'roof' ? t('scope_roof') : t('scope_target')} · {fmtNum(res.total_area_m2, 0)} m²
          </p>
          {res.candidates.length === 0 && <p className="text-sm text-bad">{t('advisor_empty')}</p>}
          <ol className="flex flex-col gap-2">
            {shown.map((c) => {
              const isOpen = open === c.item_id
              const current = res.current_panel_id === c.item_id
              return (
                <li key={c.item_id} className={cx('rounded-md border p-2', c.rank === 1 ? 'border-sun bg-sun-soft/30' : 'border-line')} data-testid={`advisor-row-${c.rank}`}>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="num w-6 shrink-0 text-center text-sm font-semibold text-ink-2">{c.rank}</span>
                    <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpen(isOpen ? null : c.item_id)}>
                      <span className="block truncate text-sm font-medium">
                        {c.name} {current && <Badge>{t('advisor_current')}</Badge>}
                      </span>
                      <span className="block text-xs text-ink-3">
                        {c.manufacturer} · {c.wp} Wp · {c.width_mm}×{c.height_mm} mm{c.weight_kg ? ` · ${fmtNum(c.weight_kg, 1)} kg` : ''} · {fmtNum(c.efficiency, 1)} % · {t(`tier_${c.tier}` as 'tier_economy')}
                      </span>
                    </button>
                    <div className="grid grid-cols-3 gap-x-3 text-right text-xs">
                      <div>
                        <div className="text-ink-3">{res.scope === 'roof' ? t('advisor_fits') : t('advisor_quoted')}</div>
                        <div className="num font-semibold">
                          {res.scope === 'roof' ? c.count_max : c.count_used} <span className="text-ink-3">/ {fmtNum(res.scope === 'roof' ? c.kwp_max : c.kwp, 2)} kWp</span>
                        </div>
                      </div>
                      <div title={t('advisor_eff_price_hint')}>
                        <div className="text-ink-3">{t('advisor_eff_price')}</div>
                        <div className="num font-semibold">{c.eur_per_wp_effective != null ? fmtNum(c.eur_per_wp_effective, 3) : '—'}</div>
                      </div>
                      <div>
                        <div className="text-ink-3">{t('lead_time')}</div>
                        <div className="num font-semibold">{c.lead_time_days} {lang === 'bg' ? 'д.' : 'd'}</div>
                      </div>
                    </div>
                    <button type="button" className={cx('btn-sm', c.rank === 1 ? 'btn-accent' : 'btn-ghost')} onClick={() => apply.mutate(c)} disabled={apply.isPending} data-testid={`advisor-apply-${c.rank}`}>
                      {apply.isPending && apply.variables?.item_id === c.item_id ? <Spinner /> : <Check className="h-4 w-4" />} {t('advisor_apply')}
                    </button>
                  </div>
                  {(c.badges.length > 0 || c.warnings.length > 0) && (
                    <div className="mt-1 flex flex-wrap gap-1 pl-9">
                      {c.badges.map((b) => (
                        <Badge key={b} tone="sun">
                          {badgeLabel[b] || b}
                        </Badge>
                      ))}
                      {c.warnings.length > 0 && <Badge tone="warn">{c.warnings.length} ⚠</Badge>}
                      {c.bifacial && <Badge>bifacial</Badge>}
                      {!c.unit_price && <Badge tone="bad">{lang === 'bg' ? 'без цена' : 'no price'}</Badge>}
                    </div>
                  )}
                  {isOpen && (
                    <div className="mt-2 grid gap-2 pl-9 text-xs md:grid-cols-2">
                      <div>
                        {c.reasons.length > 0 && <div className="font-semibold text-ink-2">{t('advisor_reasons')}</div>}
                        <ul className="list-disc pl-4 text-ink-2">
                          {c.reasons.map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                        {c.warnings.length > 0 && <div className="mt-1 font-semibold text-warn">{t('advisor_warnings')}</div>}
                        <ul className="list-disc pl-4 text-warn">
                          {c.warnings.map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </div>
                      <table className="t text-xs">
                        <tbody>
                          {c.layouts.map((l) => (
                            <tr key={l.layout_id}>
                              <td>{l.name}</td>
                              <td className="text-ink-3">
                                {fmtNum(l.area_m2, 0)} m² · {l.azimuth}° / {l.tilt}° · ×{fmtNum(l.factor, 2)}
                              </td>
                              <td>{l.orientation === 'portrait' ? t('portrait') : t('landscape')}</td>
                              <td className="num text-right">
                                {l.count_used} / {l.count_max}
                              </td>
                            </tr>
                          ))}
                          <tr>
                            <td colSpan={3} className="text-ink-3">
                              {t('unit_price')}
                            </td>
                            <td className="num text-right">{c.unit_price != null ? `${fmtNum(c.unit_price, 2)} €` : '—'}</td>
                          </tr>
                          {c.kg_m2 != null && (
                            <tr>
                              <td colSpan={3} className="text-ink-3">
                                kg/m²
                              </td>
                              <td className="num text-right">{fmtNum(c.kg_m2, 1)}</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
          {res.candidates.length > shown.length || more ? (
            <button type="button" className="btn-quiet btn-sm self-start" onClick={() => setMore(!more)}>
              {more ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />} {more ? t('show_less') : t('show_more')}
            </button>
          ) : null}
        </>
      )}
    </div>
  )
}
