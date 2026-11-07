import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Download, FileText, Package, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { Confirm, Empty, Field, Input, Select, Spinner, cx, useToast } from '@/components/ui'
import { api, del, downloadFile, errMsg, fileUrl, get } from '@/lib/api'
import { fmtDate, useT } from '@/lib/i18n'
import type { ProjectDoc, Quote } from '@/lib/types'
import type { StepCtx } from '../Project'

const UPLOAD_KINDS = ['photo', 'survey', 'contract', 'protocol', 'datasheet', 'other'] as const

function fmtSize(n: number) {
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`
  if (n > 1e3) return `${Math.round(n / 1e3)} KB`
  return `${n} B`
}

export function DocumentsStep({ ctx }: { ctx: StepCtx }) {
  const { t, lang } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const pid = ctx.project.id
  const docs = useQuery({ queryKey: ['documents', pid], queryFn: () => get<{ documents: ProjectDoc[]; kinds: { code: string; label: string; count: number }[] }>(`/api/projects/${pid}/documents`) })
  const quotes = useQuery({ queryKey: ['quotes', pid], queryFn: () => get<Quote[]>(`/api/projects/${pid}/quotes`) })
  const [kind, setKind] = useState<string>('photo')
  const [title, setTitle] = useState('')
  const [filter, setFilter] = useState<string>('')
  const [toDelete, setToDelete] = useState<ProjectDoc | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const f of Array.from(files)) {
        const fd = new FormData()
        fd.append('file', f)
        fd.append('kind', kind)
        if (title) fd.append('title', files.length > 1 ? `${title} — ${f.name}` : title)
        await api(`/api/projects/${pid}/documents`, { method: 'POST', form: fd })
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['documents', pid] })
      setTitle('')
      toast.push(lang === 'bg' ? 'Файловете са качени' : 'Files uploaded', 'ok')
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/documents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents', pid] }),
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const pkg = async (q: Quote) => {
    setBusy(`pkg-${q.id}`)
    try {
      await downloadFile(`/api/quotes/${q.id}/client-package.zip`, `Paket_klient_${q.number}-v${q.version}.zip`)
      qc.invalidateQueries({ queryKey: ['documents', pid] })
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setBusy(null)
    }
  }
  const list = (docs.data?.documents || []).filter((d) => !filter || d.kind === filter)
  const photos = list.filter((d) => d.kind === 'photo' && (d.mime || '').startsWith('image/'))
  const files = list.filter((d) => !photos.includes(d))

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4">
        <h2 className="mb-1">{t('documents_title')}</h2>
        <p className="mb-3 text-xs text-ink-3">{t('documents_hint')}</p>
        <div className="flex flex-wrap items-end gap-3">
          <Field label={t('doc_kind')}>
            <Select className="input-sm w-auto" value={kind} onChange={(e) => setKind(e.target.value)}>
              {UPLOAD_KINDS.map((k) => (
                <option key={k} value={k}>
                  {docs.data?.kinds.find((x) => x.code === k)?.label || k}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t('name')} className="min-w-[200px] flex-1">
            <Input className="input-sm" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={lang === 'bg' ? 'напр. Покрив юг, табло, електромер' : 'e.g. roof south, switchboard'} />
          </Field>
          <input ref={fileRef} type="file" multiple className="hidden" accept={kind === 'photo' ? 'image/*' : undefined} onChange={(e) => e.target.files?.length && upload.mutate(e.target.files)} data-testid="input-document-file" />
          <button type="button" className="btn-primary btn-sm" onClick={() => fileRef.current?.click()} disabled={upload.isPending} data-testid="button-upload-document">
            {upload.isPending ? <Spinner /> : kind === 'photo' ? <Camera className="h-4 w-4" /> : <Upload className="h-4 w-4" />} {t('upload')}
          </button>
          {(quotes.data || []).slice(0, 1).map((q) => (
            <button key={q.id} type="button" className="btn-accent btn-sm" onClick={() => pkg(q)} disabled={!!busy} title={t('client_package_hint')}>
              {busy === `pkg-${q.id}` ? <Spinner /> : <Package className="h-4 w-4" />} {t('client_package')} · {q.number} v{q.version}
            </button>
          ))}
        </div>
      </div>

      {docs.data && docs.data.documents.length > 0 && (
        <div className="flex flex-wrap gap-1">
          <button type="button" className={cx('btn-sm', !filter ? 'bg-ink text-white' : 'btn-ghost')} onClick={() => setFilter('')}>
            {lang === 'bg' ? 'Всички' : 'All'} ({docs.data.documents.length})
          </button>
          {docs.data.kinds
            .filter((k) => k.count > 0)
            .map((k) => (
              <button key={k.code} type="button" className={cx('btn-sm', filter === k.code ? 'bg-ink text-white' : 'btn-ghost')} onClick={() => setFilter(k.code)}>
                {k.label} ({k.count})
              </button>
            ))}
        </div>
      )}

      {docs.data && docs.data.documents.length === 0 && <Empty title={t('documents_none')} />}

      {photos.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {photos.map((d) => (
            <figure key={d.id} className="card group relative overflow-hidden">
              <a href={fileUrl(d.path)} target="_blank" rel="noopener">
                <img src={fileUrl(d.path)} alt={d.title} className="aspect-[4/3] w-full object-cover" loading="lazy" />
              </a>
              <figcaption className="flex items-center gap-1 px-2 py-1 text-xs">
                <span className="min-w-0 flex-1 truncate" title={d.title}>
                  {d.title}
                </span>
                <span className="text-ink-3">{fmtDate(d.created_at)}</span>
                <button type="button" className="btn-quiet btn-sm -mr-1 text-bad" onClick={() => setToDelete(d)} aria-label={t('delete')}>
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      {files.length > 0 && (
        <div className="card overflow-hidden">
          <table className="tbl">
            <thead>
              <tr>
                <th className="w-32">{t('doc_kind')}</th>
                <th>{t('name')}</th>
                <th className="w-28">{t('updated')}</th>
                <th className="w-20 text-right">{t('size')}</th>
                <th className="w-24" />
              </tr>
            </thead>
            <tbody>
              {files.map((d) => (
                <tr key={d.id} data-testid={`doc-${d.id}`}>
                  <td className="text-xs text-ink-2">{d.kind_label}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 shrink-0 text-ink-3" />
                      <div className="min-w-0">
                        <div className="truncate">{d.title}</div>
                        <div className="truncate text-[11px] text-ink-3">
                          {d.filename}
                          {d.notes ? ` · ${d.notes}` : ''}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="text-xs text-ink-3">{d.created_at ? new Date(d.created_at).toLocaleString('bg-BG', { dateStyle: 'short', timeStyle: 'short' }) : ''}</td>
                  <td className="num text-right text-xs">{fmtSize(d.size)}</td>
                  <td className="text-right">
                    <button type="button" className="btn-quiet btn-sm" onClick={() => downloadFile(`/api/documents/${d.id}/download`, d.filename).catch((e) => toast.push(errMsg(e), 'bad'))} aria-label={t('download')}>
                      <Download className="h-4 w-4" />
                    </button>
                    <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => setToDelete(d)} aria-label={t('delete')}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Confirm
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        onConfirm={() => {
          if (toDelete) remove.mutate(toDelete.id)
          setToDelete(null)
        }}
        title={t('delete')}
        text={toDelete?.title}
        danger
      />
    </div>
  )
}
