/* Roof photo → rectified plane → roof outline / obstacles → panel placement. */
import { Camera, Eraser, ImagePlus, RotateCcw, Save, ScanSearch, Sparkles, Undo2, Wand2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Field, NumInput, Segmented, Select, Spinner, Stat, Warn, cx, useToast } from '@/components/ui'
import { api, errMsg, fileUrl, isNative, patch, post } from '@/lib/api'
import { autoFill, polygonArea, pointInPolygon, rectifyImage, round3 } from '@/lib/geometry'
import { fmtNum, useT } from '@/lib/i18n'
import type { CatalogItem, Layout, PanelRect, Project, Pt, RoofType } from '@/lib/types'

type Mode = 'corners' | 'roof' | 'obstacle' | 'panels'

interface Draft {
  name: string
  plane_w_m: number
  plane_h_m: number
  corners: Pt[]
  roof_polygon: Pt[]
  obstacles: Pt[][]
  panels: PanelRect[]
  panel_item_id: number | null
  orientation: 'portrait' | 'landscape' | 'auto'
  gap_x_m: number
  gap_y_m: number
  setback_m: number
  row_spacing_m: number
  tilt_deg: number
  azimuth_deg: number
}

const fromLayout = (l: Layout): Draft => ({
  name: l.name,
  plane_w_m: l.plane_w_m,
  plane_h_m: l.plane_h_m,
  corners: l.corners || [],
  roof_polygon: l.roof_polygon || [],
  obstacles: l.obstacles || [],
  panels: l.panels || [],
  panel_item_id: l.panel_item_id,
  orientation: l.orientation,
  gap_x_m: l.gap_x_m,
  gap_y_m: l.gap_y_m,
  setback_m: l.setback_m,
  row_spacing_m: l.row_spacing_m,
  tilt_deg: l.tilt_deg,
  azimuth_deg: l.azimuth_deg,
})

const PANEL_FILL = 'rgba(24, 40, 72, 0.82)'
const PANEL_OFF = 'rgba(120, 120, 120, 0.35)'

export function LayoutEditor({ project, layout, items, roofType, onSaved }: { project: Project; layout: Layout; items: CatalogItem[]; roofType?: RoofType; onSaved: (l: Layout) => void }) {
  const { t, lang } = useT()
  const toast = useToast()
  const [d, setD] = useState<Draft>(() => fromLayout(layout))
  const [mode, setMode] = useState<Mode>(layout.image_path && (!layout.panels || layout.panels.length === 0) ? 'corners' : 'panels')
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [rect, setRect] = useState<HTMLCanvasElement | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [drawing, setDrawing] = useState<Pt[]>([]) // polygon in progress (roof / obstacle), metres
  const history = useRef<Draft[]>([])
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [size, setSize] = useState({ w: 600, h: 400 })

  const panels = items.filter((i) => i.category === 'panel' && i.active)
  const panel = panels.find((p) => p.id === d.panel_item_id) || panels[0]
  const pw = Number(panel?.specs?.width_mm || 1134) / 1000
  const ph = Number(panel?.specs?.height_mm || 2382) / 1000
  const wp = Number(panel?.specs?.wp || 0)

  const set = (p: Partial<Draft>, pushHistory = true) => {
    setD((prev) => {
      if (pushHistory) history.current = [...history.current.slice(-30), prev]
      return { ...prev, ...p }
    })
    setDirty(true)
  }
  const undo = () => {
    const prev = history.current.pop()
    if (prev) {
      setD(prev)
      setDirty(true)
    }
  }

  // ---------- image loading
  useEffect(() => {
    if (!layout.image_path) {
      setImg(null)
      return
    }
    const im = new Image()
    im.crossOrigin = 'anonymous'
    im.onload = () => setImg(im)
    im.onerror = () => setImg(null)
    im.src = fileUrl(layout.image_path) + `?v=${encodeURIComponent(layout.image_path)}`
  }, [layout.image_path])

  // ---------- rectification (debounced)
  useEffect(() => {
    if (!img || d.corners.length !== 4) {
      setRect(null)
      return
    }
    const id = window.setTimeout(() => {
      try {
        const maxW = 1000
        const aspect = d.plane_h_m / d.plane_w_m
        let ow = Math.min(maxW, Math.round(img.width))
        let oh = Math.round(ow * aspect)
        if (oh > 1400) {
          oh = 1400
          ow = Math.round(oh / aspect)
        }
        setRect(rectifyImage(img, d.corners, ow, oh))
      } catch {
        setRect(null)
      }
    }, 150)
    return () => window.clearTimeout(id)
  }, [img, d.corners, d.plane_w_m, d.plane_h_m])

  // ---------- sizing
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      const cw = el.clientWidth
      const maxH = Math.max(320, Math.min(window.innerHeight * 0.68, 760))
      if (mode === 'corners' && img) {
        const s = Math.min(cw / img.width, maxH / img.height)
        setSize({ w: Math.floor(img.width * s), h: Math.floor(img.height * s) })
      } else {
        const s = Math.min(cw / d.plane_w_m, maxH / d.plane_h_m)
        setSize({ w: Math.floor(d.plane_w_m * s), h: Math.floor(d.plane_h_m * s) })
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [mode, img, d.plane_w_m, d.plane_h_m])

  const scale = mode === 'corners' && img ? size.w / img.width : size.w / d.plane_w_m // px per (image px | metre)
  const roofPoly: Pt[] = useMemo(
    () =>
      d.roof_polygon.length >= 3
        ? d.roof_polygon
        : [
            [0, 0],
            [d.plane_w_m, 0],
            [d.plane_w_m, d.plane_h_m],
            [0, d.plane_h_m],
          ],
    [d.roof_polygon, d.plane_w_m, d.plane_h_m],
  )

  // ---------- drawing
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, W: number, Hh: number, forExport = false) => {
      ctx.clearRect(0, 0, W, Hh)
      if (mode === 'corners' && img && !forExport) {
        const s = W / img.width
        ctx.drawImage(img, 0, 0, img.width * s, img.height * s)
        // quad
        if (d.corners.length === 4) {
          ctx.beginPath()
          d.corners.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
          ctx.closePath()
          ctx.fillStyle = 'rgba(245, 181, 58, 0.18)'
          ctx.fill()
          ctx.lineWidth = 2
          ctx.strokeStyle = '#f5b53a'
          ctx.stroke()
          d.corners.forEach(([x, y], i) => {
            ctx.beginPath()
            ctx.arc(x * s, y * s, 11, 0, Math.PI * 2)
            ctx.fillStyle = '#1c1917'
            ctx.fill()
            ctx.lineWidth = 2.5
            ctx.strokeStyle = '#f5b53a'
            ctx.stroke()
            ctx.fillStyle = '#fff'
            ctx.font = 'bold 11px system-ui'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText(String(i + 1), x * s, y * s)
          })
        }
        return
      }
      const s = W / d.plane_w_m
      // background: rectified photo or grid
      if (rect) ctx.drawImage(rect, 0, 0, W, Hh)
      else {
        ctx.fillStyle = '#efe9df'
        ctx.fillRect(0, 0, W, Hh)
      }
      // 1 m grid
      ctx.strokeStyle = rect ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.08)'
      ctx.lineWidth = 1
      for (let x = 0; x <= d.plane_w_m + 1e-9; x += 1) {
        ctx.beginPath()
        ctx.moveTo(x * s, 0)
        ctx.lineTo(x * s, Hh)
        ctx.stroke()
      }
      for (let y = 0; y <= d.plane_h_m + 1e-9; y += 1) {
        ctx.beginPath()
        ctx.moveTo(0, y * s)
        ctx.lineTo(W, y * s)
        ctx.stroke()
      }
      // outside roof shading
      if (d.roof_polygon.length >= 3) {
        ctx.save()
        ctx.beginPath()
        ctx.rect(0, 0, W, Hh)
        d.roof_polygon.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
        ctx.closePath()
        ctx.fillStyle = 'rgba(0,0,0,0.35)'
        ctx.fill('evenodd')
        ctx.restore()
        ctx.beginPath()
        d.roof_polygon.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
        ctx.closePath()
        ctx.lineWidth = 2
        ctx.strokeStyle = '#f5b53a'
        ctx.stroke()
      }
      // setback band
      // obstacles
      for (const ob of d.obstacles) {
        ctx.beginPath()
        ob.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
        ctx.closePath()
        ctx.fillStyle = 'rgba(200, 50, 40, 0.35)'
        ctx.fill()
        ctx.lineWidth = 1.5
        ctx.strokeStyle = '#c8322a'
        ctx.stroke()
      }
      // in-progress polygon
      if (drawing.length) {
        ctx.beginPath()
        drawing.forEach(([x, y], i) => (i ? ctx.lineTo(x * s, y * s) : ctx.moveTo(x * s, y * s)))
        ctx.lineWidth = 2
        ctx.setLineDash([6, 4])
        ctx.strokeStyle = mode === 'obstacle' ? '#c8322a' : '#f5b53a'
        ctx.stroke()
        ctx.setLineDash([])
        drawing.forEach(([x, y]) => {
          ctx.beginPath()
          ctx.arc(x * s, y * s, 5, 0, Math.PI * 2)
          ctx.fillStyle = '#fff'
          ctx.fill()
          ctx.stroke()
        })
      }
      // panels
      d.panels.forEach((p, i) => {
        ctx.fillStyle = p.enabled ? PANEL_FILL : PANEL_OFF
        ctx.fillRect(p.x * s, p.y * s, p.w * s, p.h * s)
        ctx.lineWidth = 1
        ctx.strokeStyle = p.enabled ? 'rgba(255,255,255,0.8)' : 'rgba(80,80,80,0.5)'
        ctx.strokeRect(p.x * s + 0.5, p.y * s + 0.5, p.w * s - 1, p.h * s - 1)
        if (p.enabled) {
          // cell lines
          ctx.strokeStyle = 'rgba(255,255,255,0.18)'
          const cols = p.w > p.h ? 6 : 2
          const rows = p.w > p.h ? 2 : 6
          for (let c = 1; c < cols; c++) {
            ctx.beginPath()
            ctx.moveTo((p.x + (p.w * c) / cols) * s, p.y * s)
            ctx.lineTo((p.x + (p.w * c) / cols) * s, (p.y + p.h) * s)
            ctx.stroke()
          }
          for (let r = 1; r < rows; r++) {
            ctx.beginPath()
            ctx.moveTo(p.x * s, (p.y + (p.h * r) / rows) * s)
            ctx.lineTo((p.x + p.w) * s, (p.y + (p.h * r) / rows) * s)
            ctx.stroke()
          }
        }
        if (!forExport || p.enabled) {
          ctx.fillStyle = p.enabled ? 'rgba(255,255,255,0.9)' : 'rgba(60,60,60,0.7)'
          ctx.font = `${Math.max(10, Math.min(14, s * 0.25))}px system-ui`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(String(i + 1), (p.x + p.w / 2) * s, (p.y + p.h / 2) * s)
        }
      })
      // dimensions
      ctx.fillStyle = 'rgba(28,25,23,0.75)'
      ctx.font = 'bold 12px system-ui'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'top'
      ctx.fillText(`${fmtNum(d.plane_w_m, 2)} m × ${fmtNum(d.plane_h_m, 2)} m`, 6, 6)
    },
    [mode, img, rect, d, drawing],
  )

  useEffect(() => {
    const c = canvasRef.current
    if (!c) return
    const dpr = window.devicePixelRatio || 1
    c.width = size.w * dpr
    c.height = size.h * dpr
    c.style.width = `${size.w}px`
    c.style.height = `${size.h}px`
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    draw(ctx, size.w, size.h)
  }, [draw, size])

  // ---------- pointer interaction
  const drag = useRef<{ kind: 'corner' | 'panel' | 'vertex'; idx: number; sub?: number; start: Pt; orig: Pt; moved: boolean } | null>(null)
  const toLocal = (e: React.PointerEvent): Pt => {
    const r = canvasRef.current!.getBoundingClientRect()
    return [(e.clientX - r.left) / scale, (e.clientY - r.top) / scale]
  }
  const onDown = (e: React.PointerEvent) => {
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    const p = toLocal(e)
    if (mode === 'corners') {
      if (!img) return
      const tol = 24 / scale
      let best = -1
      let bd = tol
      d.corners.forEach((c, i) => {
        const dd = Math.hypot(c[0] - p[0], c[1] - p[1])
        if (dd < bd) {
          bd = dd
          best = i
        }
      })
      if (best >= 0) drag.current = { kind: 'corner', idx: best, start: p, orig: d.corners[best], moved: false }
      return
    }
    if (mode === 'panels') {
      for (let i = d.panels.length - 1; i >= 0; i--) {
        const pn = d.panels[i]
        if (p[0] >= pn.x && p[0] <= pn.x + pn.w && p[1] >= pn.y && p[1] <= pn.y + pn.h) {
          drag.current = { kind: 'panel', idx: i, start: p, orig: [pn.x, pn.y], moved: false }
          return
        }
      }
      return
    }
    if (mode === 'roof' || mode === 'obstacle') {
      // drag an existing vertex of the roof polygon?
      const tol = 14 / scale
      if (mode === 'roof' && drawing.length === 0) {
        const vi = d.roof_polygon.findIndex((v) => Math.hypot(v[0] - p[0], v[1] - p[1]) < tol)
        if (vi >= 0) {
          drag.current = { kind: 'vertex', idx: vi, start: p, orig: d.roof_polygon[vi], moved: false }
          return
        }
      }
      if (mode === 'obstacle' && drawing.length === 0) {
        for (let oi = 0; oi < d.obstacles.length; oi++) {
          const vi = d.obstacles[oi].findIndex((v) => Math.hypot(v[0] - p[0], v[1] - p[1]) < tol)
          if (vi >= 0) {
            drag.current = { kind: 'vertex', idx: oi, sub: vi, start: p, orig: d.obstacles[oi][vi], moved: false }
            return
          }
        }
      }
      // add vertex (close when clicking near the first one)
      const q: Pt = [round3(Math.max(0, Math.min(d.plane_w_m, p[0]))), round3(Math.max(0, Math.min(d.plane_h_m, p[1])))]
      if (drawing.length >= 3 && Math.hypot(drawing[0][0] - q[0], drawing[0][1] - q[1]) < tol) {
        finishPolygon()
        return
      }
      setDrawing((xs) => [...xs, q])
    }
  }
  const onMove = (e: React.PointerEvent) => {
    const dr = drag.current
    if (!dr) return
    const p = toLocal(e)
    const dx = p[0] - dr.start[0]
    const dy = p[1] - dr.start[1]
    if (Math.hypot(dx * scale, dy * scale) > 3) dr.moved = true
    if (!dr.moved) return
    if (dr.kind === 'corner') {
      const c = d.corners.map((v, i) => (i === dr.idx ? ([Math.max(0, Math.min(img!.width, dr.orig[0] + dx)), Math.max(0, Math.min(img!.height, dr.orig[1] + dy))] as Pt) : v))
      set({ corners: c }, false)
    } else if (dr.kind === 'panel') {
      const nx = Math.round((dr.orig[0] + dx) * 100) / 100
      const ny = Math.round((dr.orig[1] + dy) * 100) / 100
      set({ panels: d.panels.map((pn, i) => (i === dr.idx ? { ...pn, x: nx, y: ny } : pn)) }, false)
    } else if (dr.kind === 'vertex') {
      const q: Pt = [round3(dr.orig[0] + dx), round3(dr.orig[1] + dy)]
      if (dr.sub === undefined) set({ roof_polygon: d.roof_polygon.map((v, i) => (i === dr.idx ? q : v)) }, false)
      else set({ obstacles: d.obstacles.map((ob, oi) => (oi === dr.idx ? ob.map((v, vi) => (vi === dr.sub ? q : v)) : ob)) }, false)
    }
  }
  const onUp = () => {
    const dr = drag.current
    drag.current = null
    if (!dr) return
    if (dr.kind === 'panel' && !dr.moved) {
      set({ panels: d.panels.map((pn, i) => (i === dr.idx ? { ...pn, enabled: !pn.enabled } : pn)) })
    } else if (dr.moved) {
      history.current = [...history.current.slice(-30), d]
    }
  }
  const finishPolygon = () => {
    if (drawing.length < 3) {
      setDrawing([])
      return
    }
    if (mode === 'roof') set({ roof_polygon: drawing })
    else set({ obstacles: [...d.obstacles, drawing] })
    setDrawing([])
  }

  // ---------- actions
  const runAutofill = () => {
    const res = autoFill(roofPoly, d.obstacles, { panelW: pw, panelH: ph, orientation: d.orientation, gapX: d.gap_x_m, gapY: d.gap_y_m, setback: d.setback_m, rowSpacing: d.row_spacing_m })
    set({ panels: res.panels })
    setMode('panels')
  }
  const addPanel = () => {
    const w = d.orientation === 'landscape' ? ph : pw
    const h = d.orientation === 'landscape' ? pw : ph
    const cx0 = d.plane_w_m / 2 - w / 2
    const cy0 = d.plane_h_m / 2 - h / 2
    set({ panels: [...d.panels, { x: round3(cx0), y: round3(cy0), w, h, enabled: true }] })
    setMode('panels')
  }
  const removeDisabled = () => set({ panels: d.panels.filter((p) => p.enabled) })

  const uploadImage = async (file: File) => {
    setBusy('upload')
    try {
      const fd = new FormData()
      fd.append('file', file)
      const l = await api<Layout>(`/api/projects/${project.id}/layouts/${layout.id}/image`, { form: fd })
      onSaved(l)
      setD((prev) => ({ ...prev, corners: l.corners }))
      setMode('corners')
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setBusy(null)
    }
  }
  const takePhoto = async () => {
    try {
      const { Camera, CameraResultType, CameraSource } = await import('@capacitor/camera')
      const photo = await Camera.getPhoto({ quality: 85, resultType: CameraResultType.Uri, source: CameraSource.Prompt, correctOrientation: true })
      if (!photo.webPath) return
      const blob = await (await fetch(photo.webPath)).blob()
      await uploadImage(new File([blob], 'roof.jpg', { type: blob.type || 'image/jpeg' }))
    } catch (e) {
      if (!/cancel/i.test(String(e))) toast.push(errMsg(e), 'bad')
    }
  }
  const detectRoof = async () => {
    setBusy('detect')
    try {
      await save(false)
      const r = await post<{ corners: number[][]; confidence: number; method: string }>(`/api/projects/${project.id}/layouts/${layout.id}/detect-roof`)
      if (img) set({ corners: r.corners.map(([x, y]) => [x * img.width, y * img.height] as Pt) })
      toast.push(`${lang === 'bg' ? 'Разпознато' : 'Detected'} (${Math.round(r.confidence * 100)} %)`, 'ok')
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setBusy(null)
    }
  }
  const detectObstacles = async () => {
    setBusy('obst')
    try {
      await save(false)
      const r = await post<{ obstacles: Pt[][] }>(`/api/projects/${project.id}/layouts/${layout.id}/detect-obstacles`)
      const inside = r.obstacles.filter((ob) => ob.length >= 3 && polygonArea(ob) > 0.04 && ob.some((v) => pointInPolygon(v, roofPoly)))
      set({ obstacles: [...d.obstacles, ...inside] })
      toast.push(`${inside.length} ${lang === 'bg' ? 'препятствия' : 'obstacles'}`, inside.length ? 'ok' : 'info')
      setMode('obstacle')
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setBusy(null)
    }
  }

  const exportPng = (): string | null => {
    if (mode === 'corners') return null
    const W = 1200
    const Hh = Math.round((W * d.plane_h_m) / d.plane_w_m)
    const c = document.createElement('canvas')
    c.width = W
    c.height = Hh
    const ctx = c.getContext('2d')!
    draw(ctx, W, Hh, true)
    try {
      return c.toDataURL('image/png')
    } catch {
      return null
    }
  }

  const save = useCallback(
    async (withRender = true) => {
      setBusy('save')
      try {
        const body = { ...d, panels: d.panels, summary: undefined }
        let l = await patch<Layout>(`/api/projects/${project.id}/layouts/${layout.id}`, body)
        if (withRender) {
          const png = exportPng()
          if (png) l = await post<Layout>(`/api/projects/${project.id}/layouts/${layout.id}/render`, { png })
        }
        onSaved(l)
        setDirty(false)
        if (withRender) toast.push(t('layout_saved'), 'ok')
      } catch (e) {
        toast.push(errMsg(e), 'bad')
      } finally {
        setBusy(null)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [d, project.id, layout.id, mode, draw],
  )

  const enabled = d.panels.filter((p) => p.enabled).length
  const kwp = Math.round(enabled * wp) / 1000
  const area = polygonArea(roofPoly)

  const hint = { corners: t('tool_hint_corners'), roof: t('tool_hint_roof'), obstacle: t('tool_hint_obstacle'), panels: t('tool_hint_panels') }[mode]

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_320px]">
      <div className="flex min-w-0 flex-col gap-3">
        {/* toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            size="sm"
            value={mode}
            onChange={(m) => {
              setDrawing([])
              setMode(m)
            }}
            options={[
              { value: 'corners', label: t('tool_corners') },
              { value: 'roof', label: t('tool_roof') },
              { value: 'obstacle', label: t('tool_obstacle') },
              { value: 'panels', label: t('tool_panels') },
            ]}
          />
          <div className="ml-auto flex flex-wrap items-center gap-1">
            <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => e.target.files?.[0] && uploadImage(e.target.files[0])} />
            <button type="button" className="btn-ghost btn-sm" onClick={() => fileRef.current?.click()} disabled={!!busy} data-testid="button-upload-photo">
              {busy === 'upload' ? <Spinner /> : <ImagePlus className="h-4 w-4" />} {t('upload_photo')}
            </button>
            {isNative && (
              <button type="button" className="btn-ghost btn-sm" onClick={takePhoto} disabled={!!busy}>
                <Camera className="h-4 w-4" /> {t('take_photo')}
              </button>
            )}
            <button type="button" className="btn-quiet btn-sm" onClick={undo} disabled={history.current.length === 0} aria-label={t('undo')} title={t('undo')}>
              <Undo2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* mode actions */}
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {mode === 'corners' && (
            <>
              <button type="button" className="btn-ghost btn-sm" onClick={detectRoof} disabled={!img || !!busy} data-testid="button-detect-roof">
                {busy === 'detect' ? <Spinner /> : <ScanSearch className="h-4 w-4" />} {t('detect_roof')}
              </button>
              {img && (
                <button type="button" className="btn-quiet btn-sm" onClick={() => set({ corners: [[img.width * 0.1, img.height * 0.1], [img.width * 0.9, img.height * 0.1], [img.width * 0.9, img.height * 0.9], [img.width * 0.1, img.height * 0.9]] })}>
                  <RotateCcw className="h-4 w-4" /> {t('reset_outline')}
                </button>
              )}
            </>
          )}
          {(mode === 'roof' || mode === 'obstacle') && (
            <>
              {drawing.length > 0 && (
                <button type="button" className="btn-primary btn-sm" onClick={finishPolygon}>
                  ✓ {lang === 'bg' ? 'Затвори' : 'Close'} ({drawing.length})
                </button>
              )}
              {drawing.length > 0 && (
                <button type="button" className="btn-quiet btn-sm" onClick={() => setDrawing([])}>
                  {t('cancel')}
                </button>
              )}
              {mode === 'roof' && (
                <button type="button" className="btn-quiet btn-sm" onClick={() => set({ roof_polygon: [] })}>
                  <RotateCcw className="h-4 w-4" /> {t('reset_outline')}
                </button>
              )}
              {mode === 'obstacle' && (
                <>
                  <button type="button" className="btn-ghost btn-sm" onClick={detectObstacles} disabled={!rect || !!busy}>
                    {busy === 'obst' ? <Spinner /> : <ScanSearch className="h-4 w-4" />} {t('detect_obstacles')}
                  </button>
                  {d.obstacles.length > 0 && (
                    <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => set({ obstacles: [] })}>
                      <Eraser className="h-4 w-4" /> {t('clear_panels').replace(/панелите|panels/i, lang === 'bg' ? 'препятствията' : 'obstacles')}
                    </button>
                  )}
                </>
              )}
            </>
          )}
          {mode === 'panels' && (
            <>
              <button type="button" className="btn-accent btn-sm" onClick={runAutofill} data-testid="button-autofill">
                <Wand2 className="h-4 w-4" /> {t('autofill')}
              </button>
              <button type="button" className="btn-ghost btn-sm" onClick={addPanel}>
                {t('add_panel')}
              </button>
              {d.panels.some((p) => !p.enabled) && (
                <button type="button" className="btn-quiet btn-sm" onClick={removeDisabled}>
                  <Eraser className="h-4 w-4" /> {lang === 'bg' ? 'Премахни изключените' : 'Remove disabled'}
                </button>
              )}
              {d.panels.length > 0 && (
                <button type="button" className="btn-quiet btn-sm text-bad" onClick={() => set({ panels: [] })}>
                  {t('clear_panels')}
                </button>
              )}
            </>
          )}
          <span className="basis-full text-xs text-ink-3">{hint}</span>
        </div>

        {/* canvas */}
        <div ref={wrapRef} className="card flex items-center justify-center overflow-hidden bg-surface-2 p-2">
          {mode === 'corners' && !img ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-ink-3">
              <p className="max-w-sm">{t('no_photo')}</p>
              <button type="button" className="btn-primary" onClick={() => fileRef.current?.click()}>
                <ImagePlus className="h-4 w-4" /> {t('upload_photo')}
              </button>
            </div>
          ) : (
            <canvas
              ref={canvasRef}
              className={cx('max-w-full touch-none rounded', mode === 'panels' ? 'cursor-pointer' : 'cursor-crosshair')}
              onPointerDown={onDown}
              onPointerMove={onMove}
              onPointerUp={onUp}
              onPointerCancel={onUp}
              onDoubleClick={() => (mode === 'roof' || mode === 'obstacle') && finishPolygon()}
              data-testid="canvas-layout"
            />
          )}
        </div>
        {!rect && img && mode !== 'corners' && <Warn>{lang === 'bg' ? 'Изправеният изглед се изчислява…' : 'Computing rectified view…'}</Warn>}
      </div>

      {/* side panel */}
      <aside className="flex flex-col gap-3">
        <div className="grid grid-cols-3 gap-2">
          <Stat label={t('modules')} value={enabled} />
          <Stat label="kWp" value={fmtNum(kwp, 2)} />
          <Stat label="m²" value={fmtNum(area, 1)} />
        </div>
        <div className="card flex flex-col gap-3 p-3">
          <Field label={t('layout_name')}>
            <input className="input input-sm" value={d.name} onChange={(e) => set({ name: e.target.value }, false)} />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label={t('plane_w')}>
              <NumInput className="input-sm" value={d.plane_w_m} min={0.5} onChange={(v) => set({ plane_w_m: v })} data-testid="input-plane-w" />
            </Field>
            <Field label={t('plane_h')}>
              <NumInput className="input-sm" value={d.plane_h_m} min={0.5} onChange={(v) => set({ plane_h_m: v })} data-testid="input-plane-h" />
            </Field>
          </div>
          <Field label={t('panel_model')}>
            <Select className="input-sm" value={d.panel_item_id ?? ''} onChange={(e) => set({ panel_item_id: Number(e.target.value) })}>
              {panels.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <span className="mt-1 block text-xs text-ink-3">
              {fmtNum(pw * 1000, 0)} × {fmtNum(ph * 1000, 0)} mm · {wp} Wp
            </span>
          </Field>
          <Field label={t('orientation')}>
            <Segmented
              size="sm"
              value={d.orientation}
              onChange={(v) => set({ orientation: v })}
              options={[
                { value: 'portrait', label: t('portrait') },
                { value: 'landscape', label: t('landscape') },
                { value: 'auto', label: t('auto') },
              ]}
            />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label={t('setback')}>
              <NumInput className="input-sm" value={d.setback_m} min={0} onChange={(v) => set({ setback_m: v })} />
            </Field>
            <Field label={t('gap')}>
              <NumInput className="input-sm" value={d.gap_x_m} min={0} onChange={(v) => set({ gap_x_m: v, gap_y_m: v })} />
            </Field>
            <Field label={t('row_spacing')}>
              <NumInput className="input-sm" value={d.row_spacing_m} min={0} onChange={(v) => set({ row_spacing_m: v })} />
            </Field>
            <Field label={t('tilt')}>
              <NumInput className="input-sm" value={d.tilt_deg} min={0} max={90} onChange={(v) => set({ tilt_deg: v })} />
            </Field>
            <Field label={t('azimuth')} className="col-span-2">
              <NumInput className="input-sm" value={d.azimuth_deg} min={0} max={360} onChange={(v) => set({ azimuth_deg: v })} />
            </Field>
          </div>
          {roofType && (
            <p className="text-xs text-ink-3">
              {lang === 'bg' ? roofType.label_bg : roofType.label_en} · {roofType.rails_per_module}+ {t('rails').toLowerCase()} · {roofType.rail_stock_length_m} m
            </p>
          )}
        </div>
        <button type="button" className={cx('btn w-full', dirty ? 'btn-accent' : 'btn-ghost')} onClick={() => save(true)} disabled={!!busy} data-testid="button-save-layout">
          {busy === 'save' ? <Spinner /> : <Save className="h-4 w-4" />} {t('save_layout')}
        </button>
        {d.panels.length === 0 && (
          <button type="button" className="btn-primary w-full" onClick={runAutofill}>
            <Sparkles className="h-4 w-4" /> {t('autofill')}
          </button>
        )}
      </aside>
    </div>
  )
}
