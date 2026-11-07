import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, CheckCheck, FileSpreadsheet, PackageCheck, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Badge, Empty, Field, Input, Modal, NumInput, Select, Spinner, Stat, Textarea, Warn, cx, useToast } from '@/components/ui'
import { del, downloadFile, errMsg, get, patch, post } from '@/lib/api'
import { fmtDate, fmtMoney, fmtNum, useT, type Key } from '@/lib/i18n'
import type { PoLine, PoStatus, PurchaseOrder, Quote, Readiness } from '@/lib/types'
import type { StepCtx } from '../Project'

const PO_STATUSES: PoStatus[] = ['draft', 'sent', 'confirmed', 'partial', 'received', 'cancelled']
const TONE: Record<PoStatus, 'neutral' | 'ok' | 'warn' | 'bad' | 'sun'> = { draft: 'neutral', sent: 'sun', confirmed: 'sun', partial: 'warn', received: 'ok', cancelled: 'bad' }

export function OrdersStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const pid = ctx.project.id
  const quotes = useQuery({ queryKey: ['quotes', pid], queryFn: () => get<Quote[]>(`/api/projects/${pid}/quotes`) })
  const ready = useQuery({ queryKey: ['readiness', pid], queryFn: () => get<Readiness>(`/api/projects/${pid}/readiness`) })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['readiness', pid] })
    qc.invalidateQueries({ queryKey: ['project', pid] })
    qc.invalidateQueries({ queryKey: ['projects'] })
    qc.invalidateQueries({ queryKey: ['quotes', pid] })
    qc.invalidateQueries({ queryKey: ['documents', pid] })
  }
  const latest = quotes.data?.find((q) => q.status === 'accepted') || (quotes.data?.length ? quotes.data.reduce((a, b) => (a.id > b.id ? a : b)) : null)
  const [srcQuote, setSrcQuote] = useState<number | null>(null)
  const generate = useMutation({
    mutationFn: (qid: number) => post<PurchaseOrder[]>(`/api/quotes/${qid}/orders/generate`, {}),
    onSuccess: (pos) => {
      refresh()
      toast.push(`${pos.length} ${lang === 'bg' ? 'поръчки' : 'orders'}`, 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const r = ready.data
  const qid = srcQuote ?? latest?.id ?? null

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-0 flex-1">
          <h2 className="mb-1">{t('step_orders')}</h2>
          <p className="text-xs text-ink-3">{t('orders_generate_hint')}</p>
        </div>
        {quotes.data && quotes.data.length > 0 && (
          <Field label={t('quotes')}>
            <Select className="input-sm w-auto" value={qid ?? ''} onChange={(e) => setSrcQuote(Number(e.target.value))}>
              {quotes.data.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.number} v{q.version} · {fmtMoney(q.total)} · {t(`status_${q.status}` as Key)}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <button type="button" className="btn-primary" disabled={!qid || generate.isPending} onClick={() => qid && generate.mutate(qid)} data-testid="button-generate-orders">
          {generate.isPending ? <Spinner /> : <PackageCheck className="h-4 w-4" />} {t('orders_generate')}
        </button>
      </div>

      {r && r.items_total > 0 && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Stat label={t('readiness')} value={`${r.pct_received} %`} sub={`${r.items_received}/${r.items_total} ${t('readiness_received')}`} />
          <Stat label={t('readiness_ordered')} value={`${r.pct_ordered} %`} sub={`${r.items_ordered}/${r.items_total}`} />
          <Stat label={lang === 'bg' ? 'Стойност получено' : 'Value received'} value={fmtMoney(r.value_received)} sub={`/ ${fmtMoney(r.value_total)}`} />
          <Stat label={t('earliest_start')} value={r.ready ? (lang === 'bg' ? 'Сега' : 'Now') : r.earliest_start ? fmtDate(r.earliest_start) : '—'} sub={r.overdue.length ? `${r.overdue.length} ${t('overdue').toLowerCase()}` : undefined} />
        </div>
      )}
      {r && r.items_total > 0 && (
        <div className="h-2 overflow-hidden rounded-full bg-surface-2" aria-label={t('readiness')}>
          <div className="h-full bg-ok transition-all" style={{ width: `${r.pct_received}%` }} />
        </div>
      )}
      {r?.ready && (
        <div className="flex items-center gap-2 rounded border border-ok/30 bg-ok/10 px-3 py-2 text-sm text-ok">
          <CheckCheck className="h-4 w-4" /> {t('readiness_ready')}
        </div>
      )}
      {r && r.not_ordered.length > 0 && r.orders.length > 0 && (
        <Warn>
          <div className="font-medium">{t('readiness_not_ordered')}</div>
          <ul className="mt-1 list-disc pl-4 text-xs">
            {r.not_ordered.slice(0, 8).map((n, i) => (
              <li key={i}>
                {n.name} — {fmtNum(n.qty, 2)} {n.unit} ({n.supplier})
              </li>
            ))}
            {r.not_ordered.length > 8 && <li>… +{r.not_ordered.length - 8}</li>}
          </ul>
        </Warn>
      )}

      {ready.data && ready.data.orders.length === 0 && <Empty title={t('orders_none')} />}
      {(r?.orders || []).map((po) => (
        <OrderCard key={po.id} po={po} onChange={refresh} />
      ))}
    </div>
  )
}

export function OrderCard({ po: po0, onChange, compact }: { po: PurchaseOrder; onChange: () => void; compact?: boolean }) {
  const { t, lang } = useT()
  const toast = useToast()
  const [po, setPo] = useState(po0)
  if (po0 !== po && po0.id === po.id && (po0.lines_received !== po.lines_received || po0.status !== po.status || po0.expected_at !== po.expected_at)) setPo(po0)
  const [open, setOpen] = useState(!compact)
  const [recv, setRecv] = useState<PoLine | null>(null)
  const [recvQty, setRecvQty] = useState(0)
  const [recvNote, setRecvNote] = useState('')
  const [adding, setAdding] = useState(false)
  const [newLine, setNewLine] = useState({ name: '', unit: 'бр.', qty_ordered: 1, unit_price: 0, sku: '' })
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<PurchaseOrder | void>) => {
    setBusy(true)
    try {
      const res = await fn()
      if (res) setPo(res)
      onChange()
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setBusy(false)
    }
  }
  const update = (body: Record<string, unknown>) => run(() => patch<PurchaseOrder>(`/api/orders/${po.id}`, body))
  const openLines = po.lines.filter((l) => l.status === 'open' || l.status === 'partial')
  return (
    <div className={cx('card overflow-hidden', po.overdue && po.status !== 'received' && 'border-warn/40')} data-testid={`order-${po.number}`}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line/10 px-4 py-2.5">
        <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => setOpen(!open)}>
          <span className="num font-semibold">{po.number}</span>
          <span className="truncate font-medium">{po.supplier}</span>
          {po.project_number && compact && (
            <span className="truncate text-xs text-ink-3">
              {po.project_number} · {po.project_name}
            </span>
          )}
          <Badge tone={TONE[po.status]}>{t(`po_${po.status}` as Key)}</Badge>
          {po.overdue && po.status !== 'received' && po.status !== 'cancelled' && (
            <Badge tone="warn">
              <AlertTriangle className="mr-1 inline h-3 w-3" />
              {t('overdue')}
            </Badge>
          )}
        </button>
        <span className="num text-xs text-ink-3">
          {po.lines_received}/{po.lines_total} · {fmtMoney(po.total, po.currency)}
        </span>
        <Select className="input-sm w-auto" value={po.status} onChange={(e) => update({ status: e.target.value })} disabled={busy} aria-label={t('status')}>
          {PO_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`po_${s}` as Key)}
            </option>
          ))}
        </Select>
        <button type="button" className="btn-quiet btn-sm" title={t('order_xlsx')} onClick={() => run(() => downloadFile(`/api/orders/${po.id}/xlsx`, `${po.number}.xlsx`))} disabled={busy} data-testid={`button-po-xlsx-${po.id}`}>
          <FileSpreadsheet className="h-4 w-4" />
        </button>
        {openLines.length > 0 && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => run(() => post<PurchaseOrder>(`/api/orders/${po.id}/receive-all`, {}))} disabled={busy} data-testid={`button-receive-all-${po.id}`}>
            <CheckCheck className="h-4 w-4" /> {t('receive_all')}
          </button>
        )}
        {po.status === 'draft' && (
          <button type="button" className="btn-quiet btn-sm text-bad" title={t('delete')} onClick={() => run(() => del(`/api/orders/${po.id}`))} disabled={busy}>
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
      {open && (
        <>
          <div className="grid grid-cols-2 gap-3 px-4 py-3 md:grid-cols-4">
            <Field label={t('ordered_on')}>
              <Input type="date" className="input-sm" value={po.ordered_at || ''} onChange={(e) => update({ ordered_at: e.target.value || null })} />
            </Field>
            <Field label={t('expected')}>
              <Input type="date" className="input-sm" value={po.expected_at || ''} onChange={(e) => update({ expected_at: e.target.value || null })} />
            </Field>
            <Field label={t('supplier_ref')}>
              <Input className="input-sm" defaultValue={po.supplier_ref || ''} onBlur={(e) => e.target.value !== (po.supplier_ref || '') && update({ supplier_ref: e.target.value })} />
            </Field>
            <Field label={t('notes')}>
              <Input className="input-sm" defaultValue={po.notes || ''} onBlur={(e) => e.target.value !== (po.notes || '') && update({ notes: e.target.value })} />
            </Field>
          </div>
          <div className="overflow-x-auto">
            <table className="tbl min-w-[720px]">
              <thead>
                <tr>
                  <th className="w-28">{t('supplier_sku')}</th>
                  <th>{t('name')}</th>
                  <th className="w-24 text-right">{lang === 'bg' ? 'Поръчано' : 'Ordered'}</th>
                  <th className="w-24 text-right">{lang === 'bg' ? 'Получено' : 'Received'}</th>
                  <th className="w-28">{t('expected')}</th>
                  <th className="w-28">{t('status')}</th>
                  <th className="w-24" />
                </tr>
              </thead>
              <tbody>
                {po.lines.map((l) => (
                  <tr key={l.id} className={cx(l.status === 'received' && 'text-ink-3', l.status === 'cancelled' && 'line-through opacity-60')} data-testid={`po-line-${l.id}`}>
                    <td className="num text-xs">{l.sku || '—'}</td>
                    <td>
                      <div>{l.name}</div>
                      {l.receipts.length > 0 && (
                        <div className="text-[11px] text-ink-3">
                          {l.receipts.map((rc, i) => (
                            <span key={i} className="mr-2">
                              {fmtDate(rc.date)}: +{fmtNum(rc.qty, 2)}
                              {rc.note ? ` (${rc.note})` : ''}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="num text-right">
                      {fmtNum(l.qty_ordered, 2)} {l.unit}
                    </td>
                    <td className={cx('num text-right', l.status === 'partial' && 'text-warn', l.status === 'received' && 'text-ok')}>{fmtNum(l.qty_received, 2)}</td>
                    <td className="text-xs">
                      <Input
                        type="date"
                        className="input-sm"
                        value={l.expected_at || ''}
                        onChange={(e) => run(() => patch<PurchaseOrder>(`/api/orders/${po.id}/lines/${l.id}`, { expected_at: e.target.value || null }))}
                        disabled={busy || l.status === 'received'}
                      />
                    </td>
                    <td>
                      <span className={cx('text-xs font-medium', l.status === 'received' ? 'text-ok' : l.overdue ? 'text-bad' : l.status === 'partial' ? 'text-warn' : 'text-ink-3')}>
                        {l.overdue && l.status !== 'received' ? t('overdue') : t(`line_${l.status}` as Key)}
                      </span>
                    </td>
                    <td className="text-right">
                      {(l.status === 'open' || l.status === 'partial') && (
                        <button
                          type="button"
                          className="btn-ghost btn-sm"
                          disabled={busy}
                          onClick={() => {
                            setRecv(l)
                            setRecvQty(l.qty_open)
                            setRecvNote('')
                          }}
                          data-testid={`button-receive-${l.id}`}
                        >
                          <Check className="h-3.5 w-3.5" /> {t('receive')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2 px-4 py-2">
            <button type="button" className="btn-quiet btn-sm" onClick={() => setAdding(true)} disabled={busy}>
              <Plus className="h-4 w-4" /> {t('add_po_line')}
            </button>
            <button type="button" className="btn-quiet btn-sm" onClick={() => run(() => get<PurchaseOrder>(`/api/orders/${po.id}`))} disabled={busy} title={t('refresh')}>
              <RefreshCw className={cx('h-4 w-4', busy && 'animate-spin')} />
            </button>
          </div>
        </>
      )}

      <Modal
        open={!!recv}
        onClose={() => setRecv(null)}
        title={`${t('receive')}: ${recv?.name || ''}`}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setRecv(null)}>
              {t('cancel')}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!recv || recvQty <= 0}
              onClick={() => {
                const l = recv!
                setRecv(null)
                run(() => post<PurchaseOrder>(`/api/orders/${po.id}/lines/${l.id}/receive`, { qty: recvQty, note: recvNote || null }))
              }}
              data-testid="button-confirm-receive"
            >
              <Check className="h-4 w-4" /> {t('receive')}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('receive_qty')} hint={recv ? `${lang === 'bg' ? 'остават' : 'open'} ${fmtNum(recv.qty_open, 2)} ${recv.unit}` : undefined}>
            <NumInput value={recvQty} min={0} onChange={setRecvQty} autoFocus data-testid="input-receive-qty" />
          </Field>
          <Field label={t('notes')}>
            <Textarea value={recvNote} onChange={(e) => setRecvNote(e.target.value)} rows={2} />
          </Field>
        </div>
      </Modal>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title={t('add_po_line')}
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setAdding(false)}>
              {t('cancel')}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!newLine.name}
              onClick={() => {
                setAdding(false)
                run(() => post<PurchaseOrder>(`/api/orders/${po.id}/lines`, { ...newLine, sku: newLine.sku || null }))
                setNewLine({ name: '', unit: 'бр.', qty_ordered: 1, unit_price: 0, sku: '' })
              }}
            >
              {t('add')}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('name')} className="col-span-2">
            <Input autoFocus value={newLine.name} onChange={(e) => setNewLine({ ...newLine, name: e.target.value })} />
          </Field>
          <Field label={t('supplier_sku')}>
            <Input value={newLine.sku} onChange={(e) => setNewLine({ ...newLine, sku: e.target.value })} />
          </Field>
          <Field label={t('unit')}>
            <Input value={newLine.unit} onChange={(e) => setNewLine({ ...newLine, unit: e.target.value })} />
          </Field>
          <Field label={t('qty')}>
            <NumInput value={newLine.qty_ordered} min={0} onChange={(v) => setNewLine({ ...newLine, qty_ordered: v })} />
          </Field>
          <Field label={t('purchase_price')}>
            <NumInput value={newLine.unit_price} min={0} onChange={(v) => setNewLine({ ...newLine, unit_price: v })} />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
