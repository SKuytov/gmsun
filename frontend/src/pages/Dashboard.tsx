import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, BookOpen, Clock, FileText, Truck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge, Empty, Loading, Stat, cx } from '@/components/ui'
import { get } from '@/lib/api'
import { fmtDate, fmtMoney, fmtNum, useT } from '@/lib/i18n'
import type { Dashboard } from '@/lib/types'

const PIPE: { key: string; tone: 'neutral' | 'ok' | 'warn' | 'bad' | 'sun' }[] = [
  { key: 'draft', tone: 'neutral' },
  { key: 'quoted', tone: 'sun' },
  { key: 'accepted', tone: 'ok' },
  { key: 'ordered', tone: 'ok' },
  { key: 'done', tone: 'ok' },
  { key: 'rejected', tone: 'bad' },
  // statuses shown in the recent-projects table only
  { key: 'sent', tone: 'sun' },
  { key: 'installing', tone: 'ok' },
]

export default function DashboardPage() {
  const { t, lang } = useT()
  const q = useQuery({ queryKey: ['dashboard'], queryFn: () => get<Dashboard>('/api/dashboard'), refetchInterval: 60_000 })
  if (!q.data) return <Loading />
  const d = q.data
  const maxPipe = Math.max(1, ...Object.values(d.pipeline))
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1>{t('dashboard_title')}</h1>
          <p className="text-sm text-ink-3">{fmtDate(d.today)}</p>
        </div>
        <Link to="/" className="btn-primary btn-sm">
          {t('nav_projects')} <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={t('nav_projects')} value={fmtNum(d.projects_total)} sub={`${d.pipeline.draft || 0} ${t('status_draft').toLowerCase()}`} />
        <Stat label={t('quotes_open_value')} value={fmtMoney(d.quotes.value_open)} sub={`${d.quotes.sent} ${t('quotes').toLowerCase()}`} />
        <Stat label={t('quotes_won_value')} value={fmtMoney(d.quotes.value_won)} sub={`${d.quotes.accepted} ${t('quotes').toLowerCase()}`} />
        <Link to="/deliveries" className="block">
          <Stat label={t('nav_deliveries')} value={fmtNum(d.deliveries.open_lines)} sub={d.deliveries.overdue_lines ? `${d.deliveries.overdue_lines} ${t('overdue').toLowerCase()}` : `${d.deliveries.open_orders} ${t('orders').toLowerCase()}`} />
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <section className="card p-4">
          <h2 className="mb-3">{t('pipeline')}</h2>
          <div className="flex flex-col gap-2">
            {PIPE.slice(0, 6).map(({ key, tone }) => {
              const n = d.pipeline[key] || 0
              return (
                <div key={key} className="flex items-center gap-3 text-sm">
                  <span className="w-32 shrink-0 text-ink-2">{t(`status_${key}` as 'status_draft')}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded bg-surface-2">
                    <div className={cx('h-full rounded', tone === 'bad' ? 'bg-bad' : tone === 'ok' ? 'bg-ok' : tone === 'sun' ? 'bg-sun' : 'bg-ink-3')} style={{ width: `${(n / maxPipe) * 100}%` }} />
                  </div>
                  <span className="num w-8 text-right">{n}</span>
                </div>
              )
            })}
          </div>
        </section>

        <section className="card p-4">
          <h2 className="mb-3 flex items-center gap-2">
            <Clock className="h-4 w-4 text-ink-3" /> {t('quotes_expiring')}
          </h2>
          {d.quotes.expiring.length === 0 ? (
            <p className="text-sm text-ink-3">{t('nothing_here')}</p>
          ) : (
            <ul className="divide-y divide-line/10 text-sm">
              {d.quotes.expiring.map((x) => (
                <li key={x.id} className="flex items-center gap-3 py-2">
                  <Link to={`/projects/${x.project_id}/quote`} className="min-w-0 flex-1 hover:underline">
                    <div className="truncate font-medium">
                      {x.number} v{x.version} · {x.client_name}
                    </div>
                    <div className="truncate text-xs text-ink-3">{x.project_name}</div>
                  </Link>
                  <span className="num text-right">{fmtMoney(x.total)}</span>
                  <Badge tone={x.expired ? 'bad' : 'warn'}>
                    {x.expired ? t('expired') : t('valid_until')} {fmtDate(x.valid_until)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card p-4">
          <h2 className="mb-3 flex items-center gap-2">
            <Truck className="h-4 w-4 text-ink-3" /> {t('nav_deliveries')}
          </h2>
          {d.deliveries.overdue.length === 0 && d.deliveries.next.length === 0 ? (
            <p className="text-sm text-ink-3">{t('deliveries_none')}</p>
          ) : (
            <ul className="divide-y divide-line/10 text-sm">
              {[...d.deliveries.overdue, ...d.deliveries.next].slice(0, 8).map((l) => (
                <li key={l.id} className="flex items-center gap-3 py-2">
                  {l.overdue ? <AlertTriangle className="h-4 w-4 shrink-0 text-bad" /> : <Clock className="h-4 w-4 shrink-0 text-ink-3" />}
                  <Link to={`/projects/${l.project_id}/orders`} className="min-w-0 flex-1 hover:underline">
                    <div className="truncate font-medium">{l.name}</div>
                    <div className="truncate text-xs text-ink-3">
                      {l.order_number} · {l.supplier} · {l.project_number}
                    </div>
                  </Link>
                  <span className="num text-xs">
                    {fmtNum(l.qty_open)} {l.unit}
                  </span>
                  <Badge tone={l.overdue ? 'bad' : 'neutral'}>{l.expected_at ? fmtDate(l.expected_at) : '—'}</Badge>
                </li>
              ))}
            </ul>
          )}
          <Link to="/deliveries" className="mt-3 inline-flex items-center gap-1 text-sm text-ink-2 hover:underline">
            {t('deliveries_title')} <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </section>

        <section className="card p-4">
          <h2 className="mb-3 flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-ink-3" /> {t('catalog_health')}
          </h2>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <HealthRow n={d.catalog.no_price} label={t('no_price_items')} to="/catalog/items" bad />
            <HealthRow n={d.catalog.indicative} label={t('indicative_items')} to="/catalog/items" />
            <HealthRow n={d.catalog.unverified} label={t('unverified_items')} to="/catalog/items" />
            <HealthRow n={d.catalog.stale} label={`${t('stale_items')} (> ${d.catalog.max_age_days} ${lang === 'bg' ? 'дни' : 'days'})`} to="/catalog/items" />
          </div>
          <div className="mt-4 flex items-center justify-between gap-3 rounded-md bg-surface-2 p-3 text-sm">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-ink-3" />
              <div>
                <div className="font-medium">{t('local_docs')}</div>
                <div className="text-xs text-ink-3">
                  {d.datasheets.items_local}/{d.datasheets.items_with_url} {lang === 'bg' ? 'каталожни листа' : 'datasheets'} · {d.datasheets.library_local}/{d.datasheets.library_total} {lang === 'bg' ? 'ръководства' : 'manuals'} · {d.datasheets.size_mb} MB
                </div>
              </div>
            </div>
            <Link to="/catalog/docs" className="btn-ghost btn-sm">
              {d.datasheets.running ? t('mirror_running') : t('open')}
            </Link>
          </div>
        </section>
      </div>

      <section className="card p-4">
        <h2 className="mb-3">{t('recent_projects')}</h2>
        {d.recent_projects.length === 0 ? (
          <Empty title={t('nothing_here')} />
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>№</th>
                <th>{t('name')}</th>
                <th>{t('client')}</th>
                <th className="text-right">kWp</th>
                <th>{t('status')}</th>
                <th>{t('updated')}</th>
              </tr>
            </thead>
            <tbody>
              {d.recent_projects.map((p) => (
                <tr key={p.id}>
                  <td className="num">
                    <Link to={`/projects/${p.id}`} className="hover:underline">
                      {p.number}
                    </Link>
                  </td>
                  <td>
                    <Link to={`/projects/${p.id}`} className="hover:underline">
                      {p.name}
                    </Link>
                  </td>
                  <td>{p.client_name}</td>
                  <td className="num text-right">{p.kwp ? fmtNum(p.kwp, 1) : '—'}</td>
                  <td>
                    <Badge tone={PIPE.find((x) => x.key === p.status)?.tone || 'neutral'}>{t(`status_${p.status}` as 'status_draft')}</Badge>
                  </td>
                  <td className="text-xs text-ink-3">{p.updated_at ? fmtDate(p.updated_at) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

function HealthRow({ n, label, to, bad }: { n: number; label: string; to: string; bad?: boolean }) {
  return (
    <Link to={to} className={cx('flex items-center justify-between rounded-md border border-line/10 px-3 py-2 hover:bg-surface-2', n > 0 && bad && 'border-bad/40')}>
      <span className="text-ink-2">{label}</span>
      <span className={cx('num font-semibold', n > 0 && bad ? 'text-bad' : n > 0 ? 'text-warn' : 'text-ok')}>{n}</span>
    </Link>
  )
}
