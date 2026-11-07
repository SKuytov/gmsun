import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Check, ChevronDown, ChevronUp, Info, Plus, ShieldCheck, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Spinner, cx, useToast } from '@/components/ui'
import { errMsg, get, post } from '@/lib/api'
import { fmtMoney, useT } from '@/lib/i18n'
import type { Completeness, CompletenessFix, CompletenessItem, Quote } from '@/lib/types'

const ICON = { ok: Check, info: Info, warn: AlertTriangle, bad: XCircle } as const
const TONE = { ok: 'text-ok', info: 'text-ink-3', warn: 'text-warn', bad: 'text-bad' } as const

/** Pre-flight check of a quote with one-click fixes. `onApplied` receives the recalculated quote list invalidation. */
export function CompletenessPanel({ quote, projectId, onApplied }: { quote: Quote; projectId: number; onApplied?: () => void }) {
  const { t, lang } = useT()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const [showOk, setShowOk] = useState(false)
  const q = useQuery({ queryKey: ['completeness', quote.id, quote.updated_at], queryFn: () => get<Completeness>(`/api/quotes/${quote.id}/completeness`) })
  const apply = useMutation({
    mutationFn: (fixes: CompletenessFix[]) => post<Completeness>(`/api/quotes/${quote.id}/completeness/apply`, { fixes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['quotes', projectId] })
      qc.invalidateQueries({ queryKey: ['completeness', quote.id] })
      onApplied?.()
      toast.push(lang === 'bg' ? 'Позициите са добавени и офертата е преизчислена' : 'Items added, quote recalculated', 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const run = (f: CompletenessFix | null) => {
    if (!f) return
    if (f.type === 'add_item') apply.mutate([f])
    else if (f.type === 'step' && f.step) nav(`/projects/${projectId}/${f.step}`)
    else if (f.type === 'nav' && f.to) nav(f.to)
    else if (f.type === 'rfq') document.querySelector('[data-testid="rfq-card"]')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  if (q.isLoading || !q.data) return null
  const c = q.data
  const addable = c.items.filter((i) => i.level !== 'ok' && i.fix?.type === 'add_item' && i.level !== 'info')
  const visible = c.items.filter((i) => showOk || i.level !== 'ok')
  const tone = c.counts.bad ? 'bad' : c.counts.warn ? 'warn' : 'ok'
  return (
    <div className="card overflow-hidden" data-testid="completeness-panel">
      <div className="flex flex-wrap items-center gap-3 border-b border-line/10 px-4 py-3">
        <ShieldCheck className={cx('h-5 w-5', TONE[tone])} />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">{t('completeness')}</h3>
          <p className="text-xs text-ink-3">{t('completeness_hint')}</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={cx('num rounded-full px-2 py-0.5 font-semibold', tone === 'bad' ? 'bg-bad/10 text-bad' : tone === 'warn' ? 'bg-warn/10 text-warn' : 'bg-ok/10 text-ok')} title={t('completeness_score')}>
            {c.score} %
          </span>
          {c.counts.bad > 0 && <span className="text-bad">{c.counts.bad} ✕</span>}
          {c.counts.warn > 0 && <span className="text-warn">{c.counts.warn} !</span>}
          {c.counts.info > 0 && <span className="text-ink-3">{c.counts.info} i</span>}
          {c.ready && <span className="text-ok">{t('completeness_ready')}</span>}
        </div>
        {addable.length > 1 && (
          <button type="button" className="btn-accent btn-sm" onClick={() => apply.mutate(addable.map((i) => i.fix!))} disabled={apply.isPending} data-testid="button-fix-all">
            {apply.isPending ? <Spinner /> : <Plus className="h-4 w-4" />} {t('completeness_fix_all')} ({addable.length})
          </button>
        )}
      </div>
      <ul className="divide-y divide-line/10">
        {c.groups.map(([code, label]) => {
          const items = visible.filter((i) => i.group === code)
          if (!items.length) return null
          return (
            <li key={code} className="px-4 py-2">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</div>
              <ul className="flex flex-col gap-1.5">
                {items.map((i) => (
                  <Finding key={i.code} item={i} onFix={run} busy={apply.isPending} />
                ))}
              </ul>
            </li>
          )
        })}
      </ul>
      <button type="button" className="flex w-full items-center justify-center gap-1 px-4 py-2 text-xs text-ink-3 hover:bg-surface-2" onClick={() => setShowOk(!showOk)}>
        {showOk ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />} {showOk ? (lang === 'bg' ? 'Скрий наред' : 'Hide passed') : `${lang === 'bg' ? 'Покажи наред' : 'Show passed'} (${c.counts.ok})`}
      </button>
    </div>
  )
}

function Finding({ item, onFix, busy }: { item: CompletenessItem; onFix: (f: CompletenessFix | null) => void; busy: boolean }) {
  const { t } = useT()
  const Icon = ICON[item.level]
  const f = item.fix
  return (
    <li className="flex items-start gap-2 text-sm" data-testid={`finding-${item.code}`}>
      <Icon className={cx('mt-0.5 h-4 w-4 shrink-0', TONE[item.level])} />
      <div className="min-w-0 flex-1">
        <div className={cx(item.level === 'ok' && 'text-ink-2')}>{item.title}</div>
        {item.detail && <div className="text-xs text-ink-3">{item.detail}</div>}
        {f?.type === 'add_item' && f.name && (
          <div className="text-xs text-ink-3">
            → {f.name} × {f.qty} {f.price ? `· ${fmtMoney(f.price)}` : ''}
          </div>
        )}
      </div>
      {f && item.level !== 'ok' && (
        <button type="button" className={cx('btn-sm shrink-0', f.type === 'add_item' ? 'btn-ghost' : 'btn-quiet')} onClick={() => onFix(f)} disabled={busy} data-testid={`fix-${item.code}`}>
          {f.type === 'add_item' ? (
            <>
              <Plus className="h-3.5 w-3.5" /> {t('completeness_fix')}
            </>
          ) : (
            <>
              <ArrowRight className="h-3.5 w-3.5" /> {f.type === 'rfq' ? 'RFQ' : t('completeness_goto')}
            </>
          )}
        </button>
      )}
    </li>
  )
}
