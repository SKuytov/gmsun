/* Geometry: homography (4-point rectification), polygon tests, and the auto-fill
   algorithm mirrored from backend/app/services/layout_engine.py. All plane coordinates
   are metres, y grows downwards (towards the eave). */
import type { PanelRect, Pt } from './types'

// ---------------------------------------------------------------- homography
export type H = number[] // 3x3 row-major

/** Solve for homography mapping src[i] -> dst[i] (4 points each) via DLT + Gaussian elimination. */
export function computeHomography(src: Pt[], dst: Pt[]): H {
  const A: number[][] = []
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i]
    const [u, v] = dst[i]
    A.push([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
    A.push([0, 0, 0, -x, -y, -1, v * x, v * y, v])
  }
  // Solve A h = 0 with h[8] = 1 -> 8x8 linear system
  const M: number[][] = A.map((r) => r.slice(0, 8))
  const b: number[] = A.map((r) => -r[8])
  const h = solve(M, b)
  return [...h, 1]
}

function solve(M: number[][], b: number[]): number[] {
  const n = b.length
  const a = M.map((r, i) => [...r, b[i]])
  for (let c = 0; c < n; c++) {
    let p = c
    for (let r = c + 1; r < n; r++) if (Math.abs(a[r][c]) > Math.abs(a[p][c])) p = r
    ;[a[c], a[p]] = [a[p], a[c]]
    const piv = a[c][c] || 1e-12
    for (let r = 0; r < n; r++) {
      if (r === c) continue
      const f = a[r][c] / piv
      for (let k = c; k <= n; k++) a[r][k] -= f * a[c][k]
    }
  }
  return a.map((r, i) => r[n] / (r[i] || 1e-12))
}

export function applyH(h: H, p: Pt): Pt {
  const [x, y] = p
  const w = h[6] * x + h[7] * y + h[8]
  return [(h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w]
}

export function invertH(h: H): H {
  const [a, b, c, d, e, f, g, hh, i] = h
  const A = e * i - f * hh
  const B = -(d * i - f * g)
  const C = d * hh - e * g
  const det = a * A + b * B + c * C || 1e-12
  return [
    A / det,
    -(b * i - c * hh) / det,
    (b * f - c * e) / det,
    B / det,
    (a * i - c * g) / det,
    -(a * f - c * d) / det,
    C / det,
    -(a * hh - b * g) / det,
    (a * e - b * d) / det,
  ]
}

/** Warp an image so that the quad `corners` (image px, TL,TR,BR,BL) becomes a W×H rectangle. */
export function rectifyImage(img: HTMLImageElement | HTMLCanvasElement, corners: Pt[], outW: number, outH: number): HTMLCanvasElement {
  const src = document.createElement('canvas')
  src.width = img.width
  src.height = img.height
  const sctx = src.getContext('2d', { willReadFrequently: true })!
  sctx.drawImage(img, 0, 0)
  const sdata = sctx.getImageData(0, 0, src.width, src.height).data
  const out = document.createElement('canvas')
  out.width = outW
  out.height = outH
  const octx = out.getContext('2d')!
  const odata = octx.createImageData(outW, outH)
  const dst: Pt[] = [
    [0, 0],
    [outW, 0],
    [outW, outH],
    [0, outH],
  ]
  const hinv = computeHomography(dst, corners) // output px -> source px
  const sw = src.width
  const sh = src.height
  for (let y = 0; y < outH; y++) {
    for (let x = 0; x < outW; x++) {
      const [sx, sy] = applyH(hinv, [x + 0.5, y + 0.5])
      const o = (y * outW + x) * 4
      if (sx < 0 || sy < 0 || sx >= sw - 1 || sy >= sh - 1) {
        odata.data[o + 3] = 0
        continue
      }
      // bilinear
      const x0 = Math.floor(sx)
      const y0 = Math.floor(sy)
      const fx = sx - x0
      const fy = sy - y0
      const i00 = (y0 * sw + x0) * 4
      const i10 = i00 + 4
      const i01 = i00 + sw * 4
      const i11 = i01 + 4
      for (let c = 0; c < 3; c++) {
        odata.data[o + c] =
          sdata[i00 + c] * (1 - fx) * (1 - fy) + sdata[i10 + c] * fx * (1 - fy) + sdata[i01 + c] * (1 - fx) * fy + sdata[i11 + c] * fx * fy
      }
      odata.data[o + 3] = 255
    }
  }
  octx.putImageData(odata, 0, 0)
  return out
}

// ---------------------------------------------------------------- polygons
export function polygonArea(poly: Pt[]): number {
  let a = 0
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i]
    const [x2, y2] = poly[(i + 1) % poly.length]
    a += x1 * y2 - x2 * y1
  }
  return Math.abs(a) / 2
}

export function pointInPolygon(p: Pt, poly: Pt[]): boolean {
  const [x, y] = p
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi) inside = !inside
  }
  return inside
}

function distPointSegment(p: Pt, a: Pt, b: Pt): number {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const l2 = dx * dx + dy * dy
  if (l2 === 0) return Math.hypot(p[0] - a[0], p[1] - a[1])
  let t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
  t = Math.max(0, Math.min(1, t))
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
}

export function distPointPolygonEdges(p: Pt, poly: Pt[]): number {
  let d = Infinity
  for (let i = 0; i < poly.length; i++) d = Math.min(d, distPointSegment(p, poly[i], poly[(i + 1) % poly.length]))
  return d
}

function ccw(a: Pt, b: Pt, c: Pt) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
function segmentsIntersect(p1: Pt, p2: Pt, p3: Pt, p4: Pt) {
  const d1 = ccw(p3, p4, p1)
  const d2 = ccw(p3, p4, p2)
  const d3 = ccw(p1, p2, p3)
  const d4 = ccw(p1, p2, p4)
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
}

export function rectCorners(x: number, y: number, w: number, h: number): Pt[] {
  return [
    [x, y],
    [x + w, y],
    [x + w, y + h],
    [x, y + h],
  ]
}

export function polygonsIntersect(a: Pt[], b: Pt[]): boolean {
  for (const p of a) if (pointInPolygon(p, b)) return true
  for (const p of b) if (pointInPolygon(p, a)) return true
  for (let i = 0; i < a.length; i++)
    for (let j = 0; j < b.length; j++) if (segmentsIntersect(a[i], a[(i + 1) % a.length], b[j], b[(j + 1) % b.length])) return true
  return false
}

export function rectFits(x: number, y: number, w: number, h: number, roof: Pt[], obstacles: Pt[][], setback: number): boolean {
  const corners = rectCorners(x, y, w, h)
  for (const c of corners) {
    if (!pointInPolygon(c, roof)) return false
    if (setback > 0 && distPointPolygonEdges(c, roof) < setback - 1e-9) return false
  }
  for (const ob of obstacles) if (polygonsIntersect(corners, ob)) return false
  return true
}

// ---------------------------------------------------------------- auto-fill (mirror of Python)
export interface FillParams {
  panelW: number // short side (m)
  panelH: number // long side (m)
  orientation: 'portrait' | 'landscape' | 'auto'
  gapX: number
  gapY: number
  setback: number
  rowSpacing: number
  offsets?: number
}

function fillOrientation(roof: Pt[], obstacles: Pt[][], p: FillParams, orientation: 'portrait' | 'landscape'): PanelRect[] {
  const w = orientation === 'portrait' ? p.panelW : p.panelH
  const h = orientation === 'portrait' ? p.panelH : p.panelW
  const xs = roof.map((q) => q[0])
  const ys = roof.map((q) => q[1])
  const minx = Math.min(...xs)
  const maxx = Math.max(...xs)
  const miny = Math.min(...ys)
  const maxy = Math.max(...ys)
  const stepX = w + p.gapX
  const stepY = h + p.gapY + p.rowSpacing
  if (maxx - minx < w || maxy - miny < h) return []
  let best: PanelRect[] = []
  const nOff = Math.max(1, p.offsets ?? 6)
  for (let ix = 0; ix < nOff; ix++) {
    const ox = minx + p.setback + (stepX * ix) / nOff
    for (let iy = 0; iy < nOff; iy++) {
      const oy = miny + p.setback + (stepY * iy) / nOff
      const panels: PanelRect[] = []
      let row = 0
      let y = oy
      while (y + h <= maxy + 1e-9) {
        let x = ox
        let placed = false
        while (x + w <= maxx + 1e-9) {
          if (rectFits(x, y, w, h, roof, obstacles, p.setback)) {
            panels.push({ x: round3(x), y: round3(y), w, h, enabled: true, row })
            placed = true
          }
          x += stepX
        }
        if (placed) row++
        y += stepY
      }
      if (panels.length > best.length) best = panels
    }
  }
  return best
}

export function autoFill(roof: Pt[], obstacles: Pt[][], p: FillParams): { panels: PanelRect[]; orientation: 'portrait' | 'landscape' } {
  if (roof.length < 3) return { panels: [], orientation: 'portrait' }
  if (p.orientation === 'auto') {
    const a = fillOrientation(roof, obstacles, p, 'portrait')
    const b = fillOrientation(roof, obstacles, p, 'landscape')
    return a.length >= b.length ? { panels: a, orientation: 'portrait' } : { panels: b, orientation: 'landscape' }
  }
  return { panels: fillOrientation(roof, obstacles, p, p.orientation), orientation: p.orientation }
}

export const round3 = (v: number) => Math.round(v * 1000) / 1000

/** Rough rail summary for the live stats (server recomputes authoritative values). */
export function quickStats(panels: PanelRect[], wp: number) {
  const en = panels.filter((p) => p.enabled)
  return { count: en.length, kwp: Math.round(en.length * wp) / 1000, area: Math.round(en.reduce((s, p) => s + p.w * p.h, 0) * 100) / 100 }
}
