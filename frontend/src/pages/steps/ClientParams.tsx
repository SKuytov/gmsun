import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Field, Input, NumInput, Segmented, Select, Stat, Textarea } from '@/components/ui'
import { get } from '@/lib/api'
import { fmtNum, useT } from '@/lib/i18n'
import type { Project } from '@/lib/types'
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
