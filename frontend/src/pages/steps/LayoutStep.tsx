import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Confirm, Empty, cx, useToast } from '@/components/ui'
import { del, errMsg, post } from '@/lib/api'
import { useT } from '@/lib/i18n'
import type { Layout, Project } from '@/lib/types'
import type { StepCtx } from '../Project'
import { LayoutEditor } from './LayoutEditor'
import { ModuleAdvisor } from '@/components/ModuleAdvisor'
import type { Selections } from '@/lib/types'

export function LayoutStep({ ctx }: { ctx: StepCtx }) {
  const { t } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const p = ctx.project
  const [selId, setSelId] = useState<number | null>(p.layouts[0]?.id ?? null)
  const [toDelete, setToDelete] = useState<Layout | null>(null)
  useEffect(() => {
    if (selId === null || !p.layouts.some((l) => l.id === selId)) setSelId(p.layouts[0]?.id ?? null)
  }, [p.layouts, selId])

  const create = useMutation({
    mutationFn: () => post<Layout>(`/api/projects/${p.id}/layouts`, { name: `${t('layouts').split(' ')[0]} ${p.layouts.length + 1}`, plane_w_m: 10, plane_h_m: 6, panel_item_id: ctx.sel.panel_item_id || undefined }),
    onSuccess: (l) => {
      qc.setQueryData<Project>(['project', p.id], (old) => (old ? { ...old, layouts: [...old.layouts, l] } : old))
      setSelId(l.id)
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })
  const remove = useMutation({
    mutationFn: (lid: number) => del(`/api/projects/${p.id}/layouts/${lid}`),
    onSuccess: (_, lid) => {
      qc.setQueryData<Project>(['project', p.id], (old) => (old ? { ...old, layouts: old.layouts.filter((l) => l.id !== lid) } : old))
      qc.invalidateQueries({ queryKey: ['project', p.id] })
    },
    onError: (e) => toast.push(errMsg(e), 'bad'),
  })

  const layout = p.layouts.find((l) => l.id === selId) || null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        {p.layouts.map((l) => (
          <button
            key={l.id}
            type="button"
            onClick={() => setSelId(l.id)}
            className={cx('btn btn-sm', l.id === selId ? 'bg-ink text-white' : 'btn-ghost')}
            data-testid={`tab-layout-${l.id}`}
          >
            {l.name}
            <span className={cx('num text-xs', l.id === selId ? 'text-white/70' : 'text-ink-3')}>{l.summary?.count || 0}</span>
          </button>
        ))}
        <button type="button" className="btn-ghost btn-sm" onClick={() => create.mutate()} disabled={create.isPending} data-testid="button-add-layout">
          <Plus className="h-4 w-4" /> {t('add_layout')}
        </button>
        {layout && (
          <button type="button" className="btn-quiet btn-sm ml-auto text-bad" onClick={() => setToDelete(layout)} aria-label={t('delete')}>
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      {!layout && (
        <Empty title={t('no_photo')}>
          <button type="button" className="btn-primary" onClick={() => create.mutate()}>
            <Plus className="h-4 w-4" /> {t('add_layout')}
          </button>
        </Empty>
      )}

      {layout && (
        <LayoutEditor
          key={layout.id}
          project={p}
          layout={layout}
          items={ctx.items}
          roofType={ctx.roofTypes.find((r) => r.code === p.roof_type)}
          onSaved={(l) => {
            qc.setQueryData<Project>(['project', p.id], (old) => (old ? { ...old, layouts: old.layouts.map((x) => (x.id === l.id ? l : x)) } : old))
            qc.invalidateQueries({ queryKey: ['projects'] })
          }}
        />
      )}

      {p.layouts.length > 0 && <ModuleAdvisor project={p} onApplied={(proj) => ctx.replaceSel((proj.params?.selections as Selections) || {})} />}

      <Confirm open={!!toDelete} onClose={() => setToDelete(null)} onConfirm={() => toDelete && remove.mutate(toDelete.id)} title={t('delete')} text={`${t('confirm_delete')} ${toDelete?.name}`} danger />
    </div>
  )
}
