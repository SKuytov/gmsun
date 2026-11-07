import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Empty, Loading, Select, Stat, Toggle } from '@/components/ui'
import { get } from '@/lib/api'
import { fmtDate, fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { Awaiting, PoStatus } from '@/lib/types'
import { OrderCard } from './steps/OrdersStep'

const STATUSES: PoStatus[] = ['draft', 'sent', 'confirmed', 'partial', 'received', 'cancelled']

export default function DeliveriesPage() {
  const { t } = useT()
  const [status, setStatus] = useState<string>('')
  const [supplier, setSupplier] = useState<string>('')
  const [overdue, setOverdue] = useState(false)
  const [view, setView] = useState<'lines' | 'orders'>('lines')
  const qs = new URLSearchParams()
  if (status) qs.set('status', status)
  if (supplier) qs.set('supplier', supplier)
  if (overdue) qs.set('overdue', '1')
  const q = useQuery({ queryKey: ['awaiting', status, supplier, overdue], queryFn: () => get<Awaiting>(`/api/orders?${qs}`) })
  const all = useQuery({ queryKey: ['awaiting', '', '', false], queryFn: () => get<Awaiting>('/api/orders') })
  const suppliers = all.data?.suppliers || q.data?.suppliers || []
  if (!q.data) return <Loading />
  const d = q.data
  const lines = [...d.overdue_lines, ...d.open_lines.filter((l) => !l.overdue)]
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1>{t('deliveries_title')}</h1>
          <p className="text-sm text-ink-3">{t('deliveries_hint')}</p>
        </div>
        <button type="button" className="btn-ghost btn-sm" onClick={() => q.refetch()}>
          <RefreshCw className="h-4 w-4" /> {t('refresh')}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={t('orders')} value={fmtNum(d.orders.length)} />
        <Stat label={t('line_open')} value={fmtNum(d.open_lines.length)} />
        <Stat label={t('overdue')} value={fmtNum(d.overdue_lines.length)} sub={d.overdue_lines.length ? t('deliveries_title') : undefined} />
        <Stat label={t('by_supplier')} value={fmtNum(suppliers.length)} />
      </div>

      <div className="card flex flex-wrap items-center gap-3 p-3">
        <Select className="input-sm w-auto" value={status} onChange={(e) => setStatus(e.target.value)} data-testid="select-po-status">
          <option value="">{t('all_statuses')}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`po_${s}` as 'po_draft')}
            </option>
          ))}
        </Select>
        <Select className="input-sm w-auto" value={supplier} onChange={(e) => setSupplier(e.target.value)} data-testid="select-po-supplier">
          <option value="">{t('by_supplier')}: —</option>
          {suppliers.map((s) => (
            <option key={s.supplier} value={s.supplier}>
              {s.supplier} ({s.open_lines})
            </option>
          ))}
        </Select>
        <Toggle checked={overdue} onChange={setOverdue} label={t('only_overdue')} />
        <div className="ml-auto flex gap-1">
          <button type="button" className={view === 'lines' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'} onClick={() => setView('lines')}>
            {t('line_open')}
          </button>
          <button type="button" className={view === 'orders' ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'} onClick={() => setView('orders')}>
            {t('orders')}
          </button>
        </div>
      </div>

      {view === 'lines' &&
        (lines.length === 0 ? (
          <Empty title={t('deliveries_none')} />
        ) : (
          <div className="card overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="w-6" />
                  <th>{t('name')}</th>
                  <th>{t('supplier')}</th>
                  <th>{t('po_number')}</th>
                  <th>{t('project')}</th>
                  <th className="text-right">{t('qty')}</th>
                  <th>{t('expected')}</th>
                  <th>{t('status')}</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.id} data-testid={`await-${l.id}`}>
                    <td>{l.overdue && <AlertTriangle className="h-4 w-4 text-bad" />}</td>
                    <td>
                      <div className="font-medium">{l.name}</div>
                      {l.sku && <div className="text-[11px] text-ink-3">{l.sku}</div>}
                    </td>
                    <td className="text-sm">{l.supplier}</td>
                    <td className="num text-sm">{l.order_number}</td>
                    <td className="text-sm">
                      <Link to={`/projects/${l.project_id}/orders`} className="hover:underline">
                        {l.project_number} · {l.project_name}
                      </Link>
                    </td>
                    <td className="num text-right text-sm">
                      {fmtNum(l.qty_open)} / {fmtNum(l.qty_ordered)} {l.unit}
                    </td>
                    <td className="text-sm">{l.expected_at ? fmtDate(l.expected_at) : '—'}</td>
                    <td>
                      <Badge tone={l.overdue ? 'bad' : l.status === 'partial' ? 'warn' : 'neutral'}>{l.overdue ? t('overdue') : t(`line_${l.status}` as 'line_open')}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}

      {view === 'orders' &&
        (d.orders.length === 0 ? (
          <Empty title={t('deliveries_none')} />
        ) : (
          <div className="flex flex-col gap-3">
            {d.orders.map((po) => (
              <div key={po.id}>
                <div className="mb-1 text-xs text-ink-3">
                  <Link to={`/projects/${po.project_id}/orders`} className="hover:underline">
                    {po.project_number} · {po.project_name}
                  </Link>{' '}
                  · {fmtMoney(po.total)}
                </div>
                <OrderCard po={po} compact onChange={() => q.refetch()} />
              </div>
            ))}
          </div>
        ))}
    </div>
  )
}
