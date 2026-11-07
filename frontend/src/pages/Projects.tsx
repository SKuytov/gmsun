import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Plus, Search, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Badge, Confirm, Empty, Field, Input, Loading, Modal, NumInput, Select, useToast } from '@/components/ui'
import { del, errMsg, get, post } from '@/lib/api'
import { fmtDate, fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { Project, ProjectListItem, RoofType } from '@/lib/types'

const statusTone: Record<string, 'neutral' | 'ok' | 'warn' | 'bad' | 'sun'> = { draft: 'neutral', quoted: 'sun', sent: 'sun', accepted: 'ok', rejected: 'bad', done: 'ok' }

export default function ProjectsPage() {
  const { t, lang } = useT()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [creating, setCreating] = useState(false)
  const [toDelete, setToDelete] = useState<ProjectListItem | null>(null)
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => get<ProjectListItem[]>('/api/projects') })
  const roofTypes = useQuery({ queryKey: ['roof-types'], queryFn: () => get<RoofType[]>('/api/catalog/roof-types') })

  const [form, setForm] = useState({ name: '', client_name: '', site_address: '', phase: 3 as 1 | 3, connected_power_kw: 10, roof_type: 'tile', desired_storage_kwh: 0, purpose: 'self' })

  const create = useMutation({
    mutationFn: () => post<Project>('/api/projects', { ...form, name: form.name || form.client_name || 'Проект' }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      setCreating(false)
      nav(`/projects/${p.id}/client`)
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/projects/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const duplicate = useMutation({
    mutationFn: (id: number) => post<Project>(`/api/projects/${id}/duplicate`),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      nav(`/projects/${p.id}/client`)
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })

  const list = useMemo(() => {
    const xs = projects.data || []
    const s = q.trim().toLowerCase()
    return s ? xs.filter((p) => [p.number, p.name, p.client_name, p.site_address || ''].some((v) => v.toLowerCase().includes(s))) : xs
  }, [projects.data, q])

  const roofLabel = (code: string) => {
    const r = roofTypes.data?.find((x) => x.code === code)
    return r ? (lang === 'bg' ? r.label_bg : r.label_en) : code
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1>{t('projects_title')}</h1>
        <div className="flex flex-1 items-center justify-end gap-2 sm:flex-none">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
            <Input placeholder={t('search')} value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" data-testid="input-search" />
          </div>
          <button type="button" className="btn-accent" onClick={() => setCreating(true)} data-testid="button-new-project">
            <Plus className="h-4 w-4" /> <span className="hidden sm:inline">{t('new_project')}</span>
          </button>
        </div>
      </div>

      {projects.isLoading && <Loading label={t('loading')} />}
      {projects.data && list.length === 0 && (
        <Empty title={t('no_projects')}>
          <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" /> {t('new_project')}
          </button>
        </Empty>
      )}

      {list.length > 0 && (
        <ul className="flex flex-col gap-2 md:hidden">
          {list.map((p) => (
            <li key={p.id} className="card p-3" data-testid={`card-project-${p.id}`}>
              <Link to={`/projects/${p.id}/client`} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="num text-xs text-ink-3">{p.number}</div>
                  <div className="truncate font-medium">{p.client_name || p.name}</div>
                  {p.name && p.name !== p.client_name && <div className="truncate text-xs text-ink-3">{p.name}</div>}
                </div>
                <Badge tone={statusTone[p.status] || 'neutral'}>{t(`status_${p.status}` as 'status_draft')}</Badge>
              </Link>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
                <span>{roofLabel(p.roof_type)}</span>
                <span className="num">
                  {fmtNum(p.connected_power_kw, 1)} kW {p.phase === 1 ? '1~' : '3~'}
                  {p.kwp ? ` / ${fmtNum(p.kwp, 2)} kWp` : ''}
                </span>
                <span className="num">{p.latest_total ? fmtMoney(p.latest_total) : '—'}</span>
                <span className="ml-auto text-ink-3">{fmtDate(p.updated_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      {list.length > 0 && (
        <div className="card hidden overflow-hidden md:block">
          <div className="overflow-x-auto">
            <table className="tbl min-w-[720px]">
              <thead>
                <tr>
                  <th>{t('project_number')}</th>
                  <th>{t('client')}</th>
                  <th>{t('site')}</th>
                  <th>{t('roof_type')}</th>
                  <th className="text-right">kW / kWp</th>
                  <th className="text-right">{t('quotes')}</th>
                  <th className="text-right">{t('total')}</th>
                  <th>{t('status')}</th>
                  <th>{t('updated')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.id} data-testid={`row-project-${p.id}`}>
                    <td className="num whitespace-nowrap font-medium">
                      <Link to={`/projects/${p.id}/client`} className="hover:underline">
                        {p.number}
                      </Link>
                    </td>
                    <td>
                      <Link to={`/projects/${p.id}/client`} className="font-medium hover:underline">
                        {p.client_name || p.name}
                      </Link>
                      {p.name && p.name !== p.client_name && <div className="text-xs text-ink-3">{p.name}</div>}
                    </td>
                    <td className="max-w-[16rem] truncate text-ink-2">{p.site_address}</td>
                    <td className="text-ink-2">{roofLabel(p.roof_type)}</td>
                    <td className="num whitespace-nowrap text-right">
                      {fmtNum(p.connected_power_kw, 1)} {p.phase === 1 ? '1~' : '3~'}
                      {p.kwp ? <span className="text-ink-3"> / {fmtNum(p.kwp, 2)}</span> : null}
                    </td>
                    <td className="num text-right">{p.quote_count}</td>
                    <td className="num whitespace-nowrap text-right">{p.latest_total ? fmtMoney(p.latest_total) : '—'}</td>
                    <td>
                      <Badge tone={statusTone[p.status] || 'neutral'}>{t(`status_${p.status}` as 'status_draft')}</Badge>
                    </td>
                    <td className="whitespace-nowrap text-ink-3">{fmtDate(p.updated_at)}</td>
                    <td className="whitespace-nowrap text-right">
                      <button type="button" className="btn-quiet btn-sm" title={t('duplicate')} onClick={() => duplicate.mutate(p.id)} aria-label={t('duplicate')}>
                        <Copy className="h-4 w-4" />
                      </button>
                      <button type="button" className="btn-quiet btn-sm text-bad" title={t('delete')} onClick={() => setToDelete(p)} aria-label={t('delete')}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title={t('new_project')}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
              {t('cancel')}
            </button>
            <button type="button" className="btn-primary" onClick={() => create.mutate()} disabled={create.isPending || !form.client_name} data-testid="button-create-project">
              {t('add')}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t('client_name')} className="sm:col-span-2">
            <Input autoFocus value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} data-testid="input-client-name" />
          </Field>
          <Field label={t('site_address')} className="sm:col-span-2">
            <Input value={form.site_address} onChange={(e) => setForm({ ...form, site_address: e.target.value })} />
          </Field>
          <Field label={t('phase')}>
            <Select value={form.phase} onChange={(e) => setForm({ ...form, phase: Number(e.target.value) as 1 | 3 })}>
              <option value={1}>{t('phase_1')}</option>
              <option value={3}>{t('phase_3')}</option>
            </Select>
          </Field>
          <Field label={t('connected_power')}>
            <NumInput value={form.connected_power_kw} onChange={(v) => setForm({ ...form, connected_power_kw: v })} min={0} />
          </Field>
          <Field label={t('roof_type')}>
            <Select value={form.roof_type} onChange={(e) => setForm({ ...form, roof_type: e.target.value })}>
              {(roofTypes.data || []).map((r) => (
                <option key={r.code} value={r.code}>
                  {lang === 'bg' ? r.label_bg : r.label_en}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('storage')}>
            <NumInput value={form.desired_storage_kwh} onChange={(v) => setForm({ ...form, desired_storage_kwh: v })} min={0} />
          </Field>
        </div>
      </Modal>

      <Confirm open={!!toDelete} onClose={() => setToDelete(null)} onConfirm={() => toDelete && remove.mutate(toDelete.id)} title={t('delete')} text={`${t('confirm_delete')} ${toDelete?.number} — ${toDelete?.client_name}`} danger />
    </div>
  )
}
