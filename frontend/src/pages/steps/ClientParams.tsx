import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { ClipboardList } from 'lucide-react'
import { Field, Input, NumInput, Segmented, Select, Stat, Textarea, Toggle } from '@/components/ui'
import { get } from '@/lib/api'
import { fmtNum, useT } from '@/lib/i18n'
import type { Project, Survey } from '@/lib/types'
import type { StepCtx } from '../Project'
import { MountingSystemCard } from '@/components/MountingSystem'

type TextKeys = 'name' | 'client_name' | 'client_company' | 'client_eik' | 'client_vat' | 'client_phone' | 'client_email' | 'client_address' | 'site_address' | 'notes'

/** Text field bound to a project property, saved on blur. */
function PField({ ctx, k, label, type = 'text', className, area }: { ctx: StepCtx; k: TextKeys; label: string; type?: string; className?: string; area?: boolean }) {
  const [v, setV] = useState<string>((ctx.project[k] as string) || '')
  useEffect(() => setV((ctx.project[k] as string) || ''), [ctx.project, k])
  const commit = () => {
    if (v !== ((ctx.project[k] as string) || '')) ctx.update({ [k]: v } as Partial<Project>)
  }
  return (
    <Field label={label} className={className}>
      {area ? <Textarea value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} /> : <Input type={type} value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} data-testid={`input-${k}`} />}
    </Field>
  )
}

export function ClientStep({ ctx }: { ctx: StepCtx }) {
  const { t } = useT()
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <div className="card p-4">
        <h2 className="mb-3">{t('client')}</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <PField ctx={ctx} k="client_name" label={t('client_name')} className="sm:col-span-2" />
          <PField ctx={ctx} k="client_company" label={t('client_company')} />
          <PField ctx={ctx} k="client_eik" label={t('client_eik')} />
          <PField ctx={ctx} k="client_vat" label={t('client_vat')} />
          <PField ctx={ctx} k="client_phone" label={t('client_phone')} type="tel" />
          <PField ctx={ctx} k="client_email" label={t('client_email')} type="email" className="sm:col-span-2" />
          <PField ctx={ctx} k="client_address" label={t('client_address')} className="sm:col-span-2" />
        </div>
      </div>
      <div className="card p-4">
        <h2 className="mb-3">{t('site')}</h2>
        <div className="grid grid-cols-1 gap-3">
          <PField ctx={ctx} k="name" label={t('project_name')} />
          <PField ctx={ctx} k="site_address" label={t('site_address')} />
          <PField ctx={ctx} k="notes" label={t('notes')} area />
        </div>
      </div>
    </div>
  )
}

export function ParamsStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const p = ctx.project
  const yieldQ = useQuery({
    queryKey: ['yield', ctx.kwp, p.layouts[0]?.azimuth_deg, p.layouts[0]?.tilt_deg],
    queryFn: () => get<{ annual_kwh: number; specific_yield: number }>(`/api/sizing/yield?kwp=${ctx.kwp}&azimuth_deg=${p.layouts[0]?.azimuth_deg ?? 180}&tilt_deg=${p.layouts[0]?.tilt_deg ?? 20}`),
    enabled: ctx.kwp > 0,
  })
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_280px]">
      <div className="card p-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t('purpose')} className="sm:col-span-2">
            <Segmented
              value={p.purpose}
              onChange={(v) => ctx.update({ purpose: v })}
              options={[
                { value: 'self', label: t('purpose_self') },
                { value: 'self_sell', label: t('purpose_self_sell') },
                { value: 'sell', label: t('purpose_sell') },
              ]}
            />
          </Field>
          <Field label={t('phase')}>
            <Segmented
              value={String(p.phase)}
              onChange={(v) => ctx.update({ phase: Number(v) as 1 | 3 })}
              options={[
                { value: '1', label: t('phase_1') },
                { value: '3', label: t('phase_3') },
              ]}
            />
          </Field>
          <Field label={t('connected_power')}>
            <NumInput value={p.connected_power_kw} onChange={(v) => ctx.update({ connected_power_kw: v })} min={0} data-testid="input-connected-power" />
          </Field>
          <Field label={t('target_kwp')} hint={t('target_kwp_hint')}>
            <NumInput value={Number((p.params as Record<string, unknown>)?.target_kwp || 0) || null} onChange={(v) => ctx.update({ params: { ...(p.params || {}), target_kwp: v } })} min={0} data-testid="input-target-kwp" />
          </Field>
          <Field label={t('roof_type')}>
            <Select value={p.roof_type} onChange={(e) => ctx.update({ roof_type: e.target.value })} data-testid="select-roof-type">
              {ctx.roofTypes.map((r) => (
                <option key={r.code} value={r.code}>
                  {lang === 'bg' ? r.label_bg : r.label_en}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('voltage_class')}>
            <Segmented
              value={p.voltage_class}
              onChange={(v) => ctx.update({ voltage_class: v })}
              options={[
                { value: 'LV', label: t('lv') },
                { value: 'HV', label: t('hv') },
              ]}
            />
          </Field>
          <Field label={t('storage')}>
            <NumInput value={p.desired_storage_kwh} onChange={(v) => ctx.update({ desired_storage_kwh: v })} min={0} />
          </Field>
          <Field label={t('annual_consumption')}>
            <NumInput value={p.annual_consumption_kwh} onChange={(v) => ctx.update({ annual_consumption_kwh: v })} min={0} />
          </Field>
        </div>
        <MountingSystemCard roofType={p.roof_type} className="mt-4" />
      </div>
      <div className="lg:col-span-2">
        <SurveyCard ctx={ctx} />
      </div>
      <aside className="flex flex-col gap-2">
        <Stat label={t('modules')} value={ctx.panelQty} sub={`${fmtNum(ctx.kwp, 2)} kWp`} />
        <Stat label={t('expected_yield')} value={yieldQ.data ? `${fmtNum(yieldQ.data.annual_kwh, 0)} kWh` : '—'} sub={yieldQ.data ? `${yieldQ.data.specific_yield} kWh/kWp` : ''} />
        {p.annual_consumption_kwh && yieldQ.data ? (
          <Stat label={lang === 'bg' ? 'Покритие на консумацията' : 'Consumption coverage'} value={`${fmtNum((100 * yieldQ.data.annual_kwh) / p.annual_consumption_kwh, 0)} %`} />
        ) : null}
      </aside>
    </div>
  )
}


function SurveyText({ k, label, type = 'text', className, sv, set }: { k: keyof Survey; label: string; type?: string; className?: string; sv: Survey; set: (p: Partial<Survey>) => void }) {
  const cur = (sv[k] as string | undefined) || ''
  const [v, setV] = useState(cur)
  useEffect(() => setV(cur), [cur])
  return (
    <Field label={label} className={className}>
      <Input type={type} className="input-sm" value={v} onChange={(e) => setV(e.target.value)} onBlur={() => v !== cur && set({ [k]: v } as Partial<Survey>)} data-testid={`survey-${k}`} />
    </Field>
  )
}

/** Site survey: the facts that cause most "unforeseen" costs. Stored in project.params.survey, read by the quote check. */
export function SurveyCard({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const p = ctx.project
  const saved = ((p.params as Record<string, unknown>)?.survey as Survey) || {}
  // Local copy so that quick successive edits (select, select, number) never overwrite each other
  // while the previous PATCH is still in flight.
  const [sv, setSv] = useState<Survey>(saved)
  const svRef = useRef<Survey>(saved)
  useEffect(() => {
    svRef.current = { ...svRef.current, ...saved }
    setSv(svRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.updated_at])
  const [open, setOpen] = useState(Object.keys(saved).length > 0)
  const set = (patch: Partial<Survey>) => {
    svRef.current = { ...svRef.current, ...patch }
    setSv(svRef.current)
    ctx.update({ params: { ...(p.params || {}), survey: svRef.current } })
  }
  const T = (props: { k: keyof Survey; label: string; type?: string; className?: string }) => <SurveyText {...props} sv={sv} set={set} />
  const filled = ['building_height_m', 'roof_access', 'roof_condition', 'main_breaker_a', 'internet', 'grid_operator'].filter((k) => sv[k as keyof Survey] !== undefined && sv[k as keyof Survey] !== '' && sv[k as keyof Survey] !== null).length
  return (
    <div className="card p-4" data-testid="survey-card">
      <button type="button" className="flex w-full items-center gap-3 text-left" onClick={() => setOpen(!open)}>
        <ClipboardList className="h-5 w-5 text-ink-3" />
        <div className="min-w-0 flex-1">
          <h2>{t('survey')}</h2>
          <p className="text-xs text-ink-3">{t('survey_hint')}</p>
        </div>
        <span className="num text-xs text-ink-3">{filled}/6</span>
      </button>
      {open && (
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <T k="surveyed_at" label={t('survey_date')} type="date" />
          <Field label={t('building_height')}>
            <NumInput className="input-sm" value={sv.building_height_m ?? null} min={0} onChange={(v) => set({ building_height_m: v })} data-testid="survey-height" />
          </Field>
          <Field label={t('floors')}>
            <NumInput className="input-sm" value={sv.floors ?? null} min={0} onChange={(v) => set({ floors: v })} />
          </Field>
          <Field label={t('roof_age')}>
            <NumInput className="input-sm" value={sv.roof_age_years ?? null} min={0} onChange={(v) => set({ roof_age_years: v })} />
          </Field>
          <Field label={t('roof_access')}>
            <Select className="input-sm" value={sv.roof_access || ''} onChange={(e) => set({ roof_access: e.target.value as Survey['roof_access'] })} data-testid="survey-access">
              <option value="">—</option>
              {(['ladder', 'scaffold', 'lift', 'crane', 'internal'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`access_${o}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('roof_condition')}>
            <Select className="input-sm" value={sv.roof_condition || ''} onChange={(e) => set({ roof_condition: e.target.value as Survey['roof_condition'] })}>
              <option value="">—</option>
              {(['good', 'fair', 'poor'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`cond_${o}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('structure')}>
            <Select className="input-sm" value={sv.structure || ''} onChange={(e) => set({ structure: e.target.value as Survey['structure'] })}>
              <option value="">—</option>
              {(['concrete', 'steel', 'wood'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`struct_${o}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('shading')}>
            <Select className="input-sm" value={sv.shading || ''} onChange={(e) => set({ shading: e.target.value as Survey['shading'] })}>
              <option value="">—</option>
              {(['none', 'partial', 'strong'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`shade_${o}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('grid_operator')}>
            <Select className="input-sm" value={sv.grid_operator || ''} onChange={(e) => set({ grid_operator: e.target.value })}>
              <option value="">—</option>
              {['Електроразпределителни мрежи Запад (ЕРМ Запад)', 'Електроразпределение Север (Energo-Pro)', 'Електроразпределение Юг (EVN)', 'Златни пясъци', 'ЕСО (високо напрежение)'].map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </Select>
          </Field>
          <T k="meter_no" label={t('meter_no')} />
          <Field label={t('main_breaker')}>
            <NumInput className="input-sm" value={sv.main_breaker_a ?? null} min={0} onChange={(v) => set({ main_breaker_a: v })} data-testid="survey-breaker" />
          </Field>
          <T k="meter_location" label={t('meter_location')} />
          <Field label={t('cable_route')}>
            <NumInput className="input-sm" value={sv.cable_route_m ?? null} min={0} onChange={(v) => set({ cable_route_m: v })} />
          </Field>
          <Field label={t('internet')}>
            <Select className="input-sm" value={sv.internet || ''} onChange={(e) => set({ internet: e.target.value as Survey['internet'] })} data-testid="survey-internet">
              <option value="">—</option>
              {(['wifi', 'lan', 'none'] as const).map((o) => (
                <option key={o} value={o}>
                  {t(`net_${o}`)}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex flex-col justify-end gap-2 pb-1">
            <Toggle checked={!!sv.has_lightning_protection} onChange={(v) => set({ has_lightning_protection: v })} label={t('lps')} />
            <Toggle checked={!!sv.earth_existing} onChange={(v) => set({ earth_existing: v })} label={t('earth_existing')} />
          </div>
          <T k="cable_route_notes" label={t('cable_route_notes')} className="col-span-2 md:col-span-3" />
          <Field label={t('survey_notes')} className="col-span-2 md:col-span-4">
            <Textarea defaultValue={sv.notes || ''} rows={2} onBlur={(e) => e.target.value !== (sv.notes || '') && set({ notes: e.target.value })} />
          </Field>
          <p className="col-span-2 text-xs text-ink-3 md:col-span-4">{lang === 'bg' ? 'Снимките от огледа се качват в стъпка „Документи“ (вид: Снимка).' : 'Survey photos go to the Documents step (kind: Photo).'}</p>
        </div>
      )}
    </div>
  )
}
