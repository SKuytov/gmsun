import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, DraftingCompass, Eye, EyeOff, FileSpreadsheet, FileText, Lock, Plus, RefreshCw, Trash2, Unlock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge, Empty, Field, Input, Loading, Modal, NumInput, Select, Spinner, Stat, Textarea, Warn, cx, useToast } from '@/components/ui'
import { del, downloadFile, errMsg, get, patch, post } from '@/lib/api'
import { fmtDate, fmtMoney, fmtNum, useT, type Key } from '@/lib/i18n'
import type { Quote, QuoteLine, Selections } from '@/lib/types'
import type { StepCtx } from '../Project'

const SECTIONS = ['modules', 'inverter', 'construction', 'electrical', 'labor', 'other'] as const

function quoteFieldsFromSel(sel: Selections) {
  const s = sel as Record<string, unknown>
  return {
    markup_pct: s.markup_pct as number | undefined,
    discount_pct: s.discount_pct as number | undefined,
    vat_pct: s.vat_pct as number | undefined,
    advance_pct: s.advance_pct as number | undefined,
    valid_days: s.valid_days as number | undefined,
  }
}
function cleanSel(sel: Selections): Selections {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(sel)) if (!k.startsWith('_') && !['markup_pct', 'discount_pct', 'vat_pct', 'advance_pct', 'valid_days'].includes(k)) out[k] = v
  return out as Selections
}

export function QuoteStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const p = ctx.project
  const quotes = useQuery({ queryKey: ['quotes', p.id], queryFn: () => get<Quote[]>(`/api/projects/${p.id}/quotes`) })
  const [selId, setSelId] = useState<number | null>(null)
  useEffect(() => {
    if (quotes.data && (selId === null || !quotes.data.some((q) => q.id === selId))) setSelId(quotes.data[quotes.data.length - 1]?.id ?? null)
  }, [quotes.data, selId])

  const create = useMutation({
    mutationFn: (copyFrom?: number) => post<Quote>(`/api/projects/${p.id}/quotes`, { selections: cleanSel(ctx.sel), ...quoteFieldsFromSel(ctx.sel), copy_from_quote_id: copyFrom }),
    onSuccess: (q) => {
      qc.invalidateQueries({ queryKey: ['quotes', p.id] })
      qc.invalidateQueries({ queryKey: ['project', p.id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
      setSelId(q.id)
      toast.push(`${q.number} v${q.version}`, 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })

  const quote = quotes.data?.find((q) => q.id === selId) || null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {(quotes.data || []).map((q) => (
          <button key={q.id} type="button" onClick={() => setSelId(q.id)} className={cx('btn btn-sm', q.id === selId ? 'bg-ink text-white' : 'btn-ghost')} data-testid={`tab-quote-${q.id}`}>
            <span className="num">
              {q.number} · v{q.version}
            </span>
            <span className={cx('num text-xs', q.id === selId ? 'text-white/70' : 'text-ink-3')}>{fmtMoney(q.total)}</span>
          </button>
        ))}
        <button type="button" className="btn-accent btn-sm" onClick={() => create.mutate(selId ?? undefined)} disabled={create.isPending} data-testid="button-create-quote">
          {create.isPending ? <Spinner /> : <Plus className="h-4 w-4" />} {quotes.data?.length ? t('new_version') : t('create_quote')}
        </button>
      </div>
      {quotes.isLoading && <Loading label={t('loading')} />}
      {quotes.data && quotes.data.length === 0 && (
        <Empty title={t('no_quotes')}>
          <button type="button" className="btn-primary" onClick={() => create.mutate(undefined)} disabled={create.isPending}>
            <Plus className="h-4 w-4" /> {t('create_quote')}
          </button>
        </Empty>
      )}
      {quote && <QuoteEditor key={quote.id} quote={quote} ctx={ctx} lang={lang} />}
    </div>
  )
}

function QuoteEditor({ quote: q0, ctx, lang }: { quote: Quote; ctx: StepCtx; lang: string }) {
  const { t } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [q, setQ] = useState<Quote>(q0)
  useEffect(() => setQ(q0), [q0])
  const [adding, setAdding] = useState(false)
  const [newLine, setNewLine] = useState<{ section: string; name: string; qty: number; unit: string; unit_price: number }>({ section: 'other', name: '', qty: 1, unit: 'бр.', unit_price: 0 })
  const [showHidden, setShowHidden] = useState(false)
  const [busyDoc, setBusyDoc] = useState<string | null>(null)

  const apply = (nq: Quote) => {
    setQ(nq)
    qc.setQueryData<Quote[]>(['quotes', ctx.project.id], (old) => old?.map((x) => (x.id === nq.id ? nq : x)))
    qc.invalidateQueries({ queryKey: ['projects'] })
  }
  const useMut = <A,>(fn: (a: A) => Promise<Quote>) =>
    useMutation({
      mutationFn: fn,
      onSuccess: apply,
      onError: (e) => toast.push(errMsg(e), 'bad'),
    })
  const updateQuote = useMut((body: Record<string, unknown>) => patch<Quote>(`/api/quotes/${q.id}`, body))
  const updateLine = useMut(({ id, ...body }: { id: number } & Partial<QuoteLine>) => patch<Quote>(`/api/quotes/${q.id}/lines/${id}`, body))
  const deleteLine = useMut((id: number) => del<Quote>(`/api/quotes/${q.id}/lines/${id}`))
  const addLine = useMut((body: typeof newLine) => post<Quote>(`/api/quotes/${q.id}/lines`, body))
  const recalc = useMut(() => post<Quote>(`/api/quotes/${q.id}/recalculate`))
  const resync = useMut(() => patch<Quote>(`/api/quotes/${q.id}`, { selections: cleanSel(ctx.sel), ...quoteFieldsFromSel(ctx.sel) }))

  const doc = async (kind: 'pdf' | 'pdf_internal' | 'xlsx' | 'techfile') => {
    setBusyDoc(kind)
    try {
      const base = `${q.number}-v${q.version}`
      if (kind === 'xlsx') await downloadFile(`/api/quotes/${q.id}/xlsx`, `${base}.xlsx`)
      else if (kind === 'techfile') await downloadFile(`/api/quotes/${q.id}/techfile.pdf`, `${base}-techfile.pdf`)
      else await downloadFile(`/api/quotes/${q.id}/pdf?mode=${kind === 'pdf' ? 'client' : 'internal'}`, `${base}${kind === 'pdf_internal' ? '-internal' : ''}.pdf`)
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setBusyDoc(null)
    }
  }

  const lines = q.lines.filter((l) => showHidden || !l.hidden)
  const info = (q.selections._info || {}) as Record<string, unknown>
  const stats = info.mounting_stats as Record<string, number> | undefined
  const busy = updateLine.isPending || deleteLine.isPending || recalc.isPending || updateQuote.isPending

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_300px]">
      <div className="flex min-w-0 flex-col gap-3">
        <div className="card flex flex-wrap items-center gap-2 p-3">
          <Field label={t('status')}>
            <Select className="input-sm w-auto" value={q.status} onChange={(e) => updateQuote.mutate({ status: e.target.value, recalc: false })}>
              {['draft', 'sent', 'accepted', 'rejected'].map((s) => (
                <option key={s} value={s}>
                  {t(`status_${s}` as Key)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('markup')}>
            <NumInput className="input-sm w-20" value={q.markup_pct} min={0} onChange={(v) => updateQuote.mutate({ markup_pct: v })} />
          </Field>
          <Field label={t('discount')}>
            <NumInput className="input-sm w-20" value={q.discount_pct} min={0} max={100} onChange={(v) => updateQuote.mutate({ discount_pct: v })} />
          </Field>
          <Field label={t('vat')}>
            <NumInput className="input-sm w-20" value={q.vat_pct} min={0} onChange={(v) => updateQuote.mutate({ vat_pct: v })} />
          </Field>
          <Field label={t('advance')}>
            <NumInput className="input-sm w-20" value={q.advance_pct} min={0} max={100} onChange={(v) => updateQuote.mutate({ advance_pct: v })} />
          </Field>
          <Field label={t('validity')}>
            <NumInput className="input-sm w-20" value={q.valid_days} min={1} onChange={(v) => updateQuote.mutate({ valid_days: Math.round(v) })} />
          </Field>
          <div className="ml-auto flex items-center gap-1 self-end">
            <button type="button" className="btn-ghost btn-sm" onClick={() => resync.mutate(undefined)} disabled={busy} title={lang === 'bg' ? 'Прилага текущите избори от стъпките и преизчислява' : 'Apply current step selections and recalculate'} data-testid="button-resync">
              <RefreshCw className={cx('h-4 w-4', resync.isPending && 'animate-spin')} /> {t('recalculate')}
            </button>
          </div>
        </div>

        {q.warnings.length > 0 && (
          <Warn>
            <ul className="list-disc pl-4">
              {q.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Warn>
        )}

        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="tbl min-w-[720px]">
              <thead>
                <tr>
                  <th className="w-8">№</th>
                  <th className="min-w-[200px]">{t('name')}</th>
                  <th className="w-16">{t('unit')}</th>
                  <th className="w-24 text-right">{t('qty')}</th>
                  <th className="w-28 text-right">{t('unit_price')}</th>
                  <th className="w-28 text-right">{t('total')}</th>
                  <th className="w-28" />
                </tr>
              </thead>
              <tbody>
                {SECTIONS.map((sec) => {
                  const ls = lines.filter((l) => l.section === sec)
                  if (!ls.length) return null
                  const sum = ls.filter((l) => !l.hidden).reduce((s, l) => s + l.total, 0)
                  return [
                    <tr key={`h-${sec}`} className="bg-sun-soft/60">
                      <td colSpan={5} className="py-1.5 text-xs font-semibold uppercase tracking-wide text-sun-ink">
                        {t(`section_${sec}` as Key)}
                      </td>
                      <td className="num py-1.5 text-right text-sm font-semibold">{fmtMoney(sum, '')}</td>
                      <td />
                    </tr>,
                    ...ls.map((l, i) => (
                      <tr key={l.id} className={cx(l.hidden && 'opacity-50')} data-testid={`row-line-${l.id}`}>
                        <td className="num text-ink-3">{i + 1}</td>
                        <td>
                          <input className="cell-input" defaultValue={l.name} key={`${l.id}-${l.name}`} onBlur={(e) => e.target.value !== l.name && updateLine.mutate({ id: l.id, name: e.target.value })} aria-label={t('name')} />
                        </td>
                        <td>
                          <input className="cell-input" defaultValue={l.unit} key={`${l.id}-${l.unit}`} onBlur={(e) => e.target.value !== l.unit && updateLine.mutate({ id: l.id, unit: e.target.value })} aria-label={t('unit')} />
                        </td>
                        <td>
                          <NumInput className="cell-input" value={l.qty} min={0} onChange={(v) => v !== l.qty && updateLine.mutate({ id: l.id, qty: v })} aria-label={t('qty')} />
                        </td>
                        <td>
                          <NumInput className="cell-input" value={l.unit_price} min={0} onChange={(v) => v !== l.unit_price && updateLine.mutate({ id: l.id, unit_price: v })} aria-label={t('unit_price')} />
                        </td>
                        <td className="num text-right font-medium">{fmtMoney(l.total, '')}</td>
                        <td className="whitespace-nowrap text-right">
                          <button type="button" className="btn-quiet btn-sm h-7 w-7 px-0" title={l.locked ? t('locked') : 'auto'} onClick={() => updateLine.mutate({ id: l.id, locked: !l.locked })} aria-label={t('locked')}>
                            {l.locked ? <Lock className="h-3.5 w-3.5 text-sun-ink" /> : <Unlock className="h-3.5 w-3.5 text-ink-3" />}
                          </button>
                          <button type="button" className="btn-quiet btn-sm h-7 w-7 px-0" title={t('hidden')} onClick={() => updateLine.mutate({ id: l.id, hidden: !l.hidden })} aria-label={t('hidden')}>
                            {l.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5 text-ink-3" />}
                          </button>
                          <button type="button" className="btn-quiet btn-sm h-7 w-7 px-0 text-bad" title={t('delete')} onClick={() => deleteLine.mutate(l.id)} aria-label={t('delete')}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    )),
                  ]
                })}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-line/10 p-2">
            <button type="button" className="btn-ghost btn-sm" onClick={() => setAdding(true)} data-testid="button-add-line">
              <Plus className="h-4 w-4" /> {t('add_line')}
            </button>
            <label className="ml-auto flex items-center gap-1.5 text-xs text-ink-3">
              <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> {t('hidden')}
            </label>
            {busy && <Spinner className="text-ink-3" />}
          </div>
        </div>

        <Field label={t('notes')}>
          <Textarea defaultValue={q.notes || ''} key={`notes-${q.id}-${q.notes}`} onBlur={(e) => e.target.value !== (q.notes || '') && updateQuote.mutate({ notes: e.target.value, recalc: false })} />
        </Field>
      </div>

      <aside className="flex flex-col gap-3">
        <div className="card flex flex-col gap-2 p-4">
          <Row label={t('net')} value={fmtMoney(q.net_total)} strong />
          {q.discount_amount > 0 && <Row label={`${t('discount')} ${q.discount_pct}%`} value={`− ${fmtMoney(q.discount_amount)}`} />}
          <Row label={`${t('vat_amount')} ${q.vat_pct}%`} value={fmtMoney(q.vat_amount)} />
          <Row label={t('gross')} value={fmtMoney(q.total)} strong big />
          <hr className="my-1 border-line/10" />
          <Row label={`${t('advance_amount')} ${q.advance_pct}%`} value={fmtMoney(q.advance_amount)} />
          <Row label={t('balance')} value={fmtMoney(q.balance_amount)} />
          <hr className="my-1 border-line/10" />
          <Row label={t('cost')} value={fmtMoney(q.cost_total)} muted />
          <Row label={t('margin')} value={`${fmtMoney(q.margin)} (${q.cost_total ? fmtNum((100 * q.margin) / q.net_total, 1) : '—'} %)`} muted />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Stat label={t('modules')} value={String(info.panel_qty ?? ctx.panelQty)} sub={`${fmtNum(Number(info.kwp ?? ctx.kwp), 2)} kWp`} />
          <Stat label={t('battery')} value={info.storage_kwh ? `${fmtNum(Number(info.storage_kwh), 1)} kWh` : '—'} />
          {stats && <Stat label={t('rails')} value={`${stats.rail_pieces} × ${fmtNum(stats.rail_m, 0)} m`} sub={`${stats.fixations} ${lang === 'bg' ? 'куки' : 'hooks'} · ${stats.mid_clamps + stats.end_clamps} ${lang === 'bg' ? 'скоби' : 'clamps'}`} />}
          {q.execution_days && <Stat label={t('days')} value={`${q.execution_days} × ${q.workers}`} />}
        </div>
        <div className="card flex flex-col gap-2 p-3">
          <button type="button" className="btn-primary w-full" onClick={() => doc('pdf')} disabled={!!busyDoc} data-testid="button-pdf">
            {busyDoc === 'pdf' ? <Spinner /> : <FileText className="h-4 w-4" />} {t('pdf_client')}
          </button>
          <button type="button" className="btn-ghost w-full" onClick={() => doc('pdf_internal')} disabled={!!busyDoc}>
            {busyDoc === 'pdf_internal' ? <Spinner /> : <Download className="h-4 w-4" />} {t('pdf_internal')}
          </button>
          <button type="button" className="btn-ghost w-full" onClick={() => doc('xlsx')} disabled={!!busyDoc} data-testid="button-xlsx">
            {busyDoc === 'xlsx' ? <Spinner /> : <FileSpreadsheet className="h-4 w-4" />} {t('xlsx')}
          </button>
          <button type="button" className="btn-ghost w-full" onClick={() => doc('techfile')} disabled={!!busyDoc} data-testid="button-techfile">
            {busyDoc === 'techfile' ? <Spinner /> : <DraftingCompass className="h-4 w-4" />} {t('techfile_pdf')}
          </button>
          <p className="text-center text-xs text-ink-3">
            {q.number} · v{q.version} · {fmtDate(q.created_at)} <Badge tone="neutral">{t(`status_${q.status}` as Key)}</Badge>
          </p>
        </div>
      </aside>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title={t('add_line')}
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
                addLine.mutate(newLine)
                setAdding(false)
                setNewLine({ section: 'other', name: '', qty: 1, unit: 'бр.', unit_price: 0 })
              }}
              data-testid="button-save-line"
            >
              {t('add')}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('category')} className="col-span-2">
            <Select value={newLine.section} onChange={(e) => setNewLine({ ...newLine, section: e.target.value })}>
              {SECTIONS.map((s) => (
                <option key={s} value={s}>
                  {t(`section_${s}` as Key)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('name')} className="col-span-2">
            <Input autoFocus value={newLine.name} onChange={(e) => setNewLine({ ...newLine, name: e.target.value })} data-testid="input-line-name" />
          </Field>
          <Field label={t('qty')}>
            <NumInput value={newLine.qty} min={0} onChange={(v) => setNewLine({ ...newLine, qty: v })} />
          </Field>
          <Field label={t('unit')}>
            <Input value={newLine.unit} onChange={(e) => setNewLine({ ...newLine, unit: e.target.value })} />
          </Field>
          <Field label={t('unit_price')} className="col-span-2">
            <NumInput value={newLine.unit_price} min={0} onChange={(v) => setNewLine({ ...newLine, unit_price: v })} data-testid="input-line-price" />
          </Field>
        </div>
      </Modal>
    </div>
  )
}

function Row({ label, value, strong, big, muted }: { label: string; value: string; strong?: boolean; big?: boolean; muted?: boolean }) {
  return (
    <div className={cx('flex items-baseline justify-between gap-3', muted && 'text-ink-3')}>
      <span className="text-sm">{label}</span>
      <span className={cx('num whitespace-nowrap', strong && 'font-semibold', big && 'text-lg')}>{value}</span>
    </div>
  )
}
