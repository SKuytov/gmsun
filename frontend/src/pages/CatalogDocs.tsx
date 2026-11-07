import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CloudDownload, ExternalLink, FileText, HardDrive } from 'lucide-react'
import { useState } from 'react'
import { Badge, Input, Loading, Spinner, Stat, cx, useToast } from '@/components/ui'
import { apiUrl, downloadFile, errMsg, get, post } from '@/lib/api'
import { fmtNum, useT } from '@/lib/i18n'
import type { DatasheetStatus } from '@/lib/types'

interface Library {
  items: { id: number; category: string; name: string; manufacturer: string | null; local: boolean; size: number; url: string | null; source_url: string | null }[]
  library: { system: string; doc: string; url: string; title: string; local: boolean; file: string | null; size: number }[]
}

export function DocsTab({ lang }: { lang: 'bg' | 'en' }) {
  const { t } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const status = useQuery({
    queryKey: ['datasheets', 'status'],
    queryFn: () => get<DatasheetStatus>('/api/catalog/datasheets/status'),
    refetchInterval: (q) => (q.state.data?.running ? 3000 : false),
  })
  const lib = useQuery({ queryKey: ['datasheets', 'library', status.data?.running], queryFn: () => get<Library>('/api/catalog/datasheets/library') })
  const mirror = useMutation({
    mutationFn: (onlyMissing: boolean) => post(`/api/catalog/datasheets/mirror?only_missing=${onlyMissing ? 1 : 0}`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['datasheets'] })
      toast.push(lang === 'bg' ? 'Свалянето започна на сървъра' : 'Download started on the server', 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  if (!status.data) return <Loading />
  const s = status.data
  const p = s.progress
  const needle = search.trim().toLowerCase()
  const items = (lib.data?.items || []).filter((x) => !needle || `${x.name} ${x.manufacturer || ''} ${x.category}`.toLowerCase().includes(needle))
  const manuals = (lib.data?.library || []).filter((x) => !needle || `${x.title} ${x.system} ${x.doc}`.toLowerCase().includes(needle))
  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2">
              <HardDrive className="h-5 w-5 text-ink-3" /> {t('local_docs')}
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-ink-3">{t('local_docs_hint')}</p>
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn-primary btn-sm" disabled={s.running || mirror.isPending} onClick={() => mirror.mutate(true)} data-testid="button-mirror">
              {s.running ? <Spinner /> : <CloudDownload className="h-4 w-4" />} {s.running ? t('mirror_running') : t('mirror_all')}
            </button>
            <button type="button" className="btn-ghost btn-sm" disabled={s.running || mirror.isPending} onClick={() => mirror.mutate(false)} title={lang === 'bg' ? 'Презапиши всички файлове отново' : 'Re-download everything'}>
              {t('refresh')}
            </button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label={lang === 'bg' ? 'Каталожни листове' : 'Datasheets'} value={`${s.items_local} / ${s.items_with_url}`} sub={s.items_uploaded_only ? `+${s.items_uploaded_only} ${lang === 'bg' ? 'качени ръчно' : 'uploaded manually'}` : undefined} />
          <Stat label={lang === 'bg' ? 'Ръководства за монтаж' : 'Installation manuals'} value={`${s.library_local} / ${s.library_total}`} />
          <Stat label={lang === 'bg' ? 'Файлове на диска' : 'Files on disk'} value={fmtNum(s.files)} sub={`${s.size_mb} MB`} />
          <Stat label={lang === 'bg' ? 'Последно сваляне' : 'Last download'} value={p.finished_at ? new Date(p.finished_at).toLocaleDateString('bg-BG') : '—'} sub={p.failed ? `${p.failed} ${lang === 'bg' ? 'грешки' : 'errors'}` : undefined} />
        </div>
        {s.running && (
          <div className="mt-4">
            <div className="mb-1 flex justify-between text-xs text-ink-3">
              <span className="truncate">{p.current || ''}</span>
              <span className="num">
                {p.done} / {p.total}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-surface-2">
              <div className="h-full bg-sun transition-all" style={{ width: `${p.total ? (p.done / p.total) * 100 : 0}%` }} />
            </div>
          </div>
        )}
        {!s.running && p.errors.length > 0 && (
          <details className="mt-3 text-xs text-ink-3">
            <summary className="cursor-pointer">
              {p.errors.length} {lang === 'bg' ? 'файла не можаха да се свалят' : 'files could not be downloaded'}
            </summary>
            <ul className="mt-1 list-disc pl-5">
              {p.errors.slice(0, 30).map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </details>
        )}
      </div>

      <Input className="input-sm max-w-sm" placeholder={t('search')} value={search} onChange={(e) => setSearch(e.target.value)} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="card overflow-hidden">
          <h3 className="border-b border-line/10 px-4 py-2 text-sm font-semibold">
            {lang === 'bg' ? 'Каталожни листове на артикулите' : 'Item datasheets'} ({items.length})
          </h3>
          <ul className="max-h-[60vh] divide-y divide-line/10 overflow-y-auto text-sm">
            {items.map((x) => (
              <li key={x.id} className="flex items-center gap-2 px-4 py-2">
                {x.local ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" /> : <FileText className="h-4 w-4 shrink-0 text-ink-3" />}
                <div className="min-w-0 flex-1">
                  <div className="truncate">{x.name}</div>
                  <div className="truncate text-[11px] text-ink-3">
                    {x.manufacturer || ''} · {x.category}
                  </div>
                </div>
                {x.local && x.url ? (
                  <button type="button" className="btn-quiet btn-sm" onClick={() => downloadFile(x.url!, `${x.name.slice(0, 60)}.pdf`).catch((e) => toast.push(errMsg(e), 'bad'))}>
                    PDF
                  </button>
                ) : x.source_url ? (
                  <a href={x.source_url} target="_blank" rel="noopener" className={cx('btn-quiet btn-sm text-ink-3')} title={lang === 'bg' ? 'Още не е свален локално' : 'Not mirrored yet'}>
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                ) : (
                  <Badge tone="neutral">—</Badge>
                )}
              </li>
            ))}
          </ul>
        </section>
        <section className="card overflow-hidden">
          <h3 className="border-b border-line/10 px-4 py-2 text-sm font-semibold">
            {lang === 'bg' ? 'Ръководства и сертификати (Aerocompact)' : 'Manuals & certificates (Aerocompact)'} ({manuals.length})
          </h3>
          <ul className="max-h-[60vh] divide-y divide-line/10 overflow-y-auto text-sm">
            {manuals.map((x) => (
              <li key={`${x.system}-${x.doc}`} className="flex items-center gap-2 px-4 py-2">
                {x.local ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" /> : <FileText className="h-4 w-4 shrink-0 text-ink-3" />}
                <div className="min-w-0 flex-1">
                  <div className="truncate">{x.title}</div>
                  <div className="truncate text-[11px] text-ink-3">
                    {x.system} · {x.doc}
                    {x.size ? ` · ${Math.round(x.size / 1024)} KB` : ''}
                  </div>
                </div>
                <a href={x.local && x.file ? apiUrl(x.file) : x.url} target="_blank" rel="noopener" className={cx('btn-quiet btn-sm', !x.local && 'text-ink-3')}>
                  {x.local ? 'PDF' : <ExternalLink className="h-3.5 w-3.5" />}
                </a>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
