/* 3D view of the PV plant (three.js): building, tilted roof planes (textured with the rectified photo when there is one),
   modules with glass/frame materials, obstacles, sun position by hour/month with shadows, screenshot for the documents. */
import { useQuery } from '@tanstack/react-query'
import { Camera, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Spinner, Toggle, cx, useToast } from '@/components/ui'
import { errMsg, fileUrl, get, post } from '@/lib/api'
import { fmtNum, useT } from '@/lib/i18n'
import type { Layout, Project, Scene, ScenePlane } from '@/lib/types'

const DEG = Math.PI / 180

/** Basis of a plane in world space. X = east, Y = up, Z = south. (u along the eave to the right as seen from outside,
 *  v down the slope from ridge to eave – the same (x, y) the layout editor uses.) */
function planeBasis(pl: ScenePlane, flat: boolean) {
  const az = pl.azimuth * DEG
  const tilt = (flat ? 0 : pl.tilt) * DEG
  const d = new THREE.Vector3(Math.sin(az), 0, -Math.cos(az)) // horizontal direction the plane faces (az 180 → +Z south)
  const up = new THREE.Vector3(0, 1, 0)
  const e = new THREE.Vector3().crossVectors(d.clone().negate(), up).normalize() // along the eave, to the right
  const s = d
    .clone()
    .multiplyScalar(-Math.cos(tilt))
    .add(up.clone().multiplyScalar(Math.sin(tilt))) // up the slope
  // eave left corner
  const origin = flat
    ? d.clone().multiplyScalar(pl.height_m / 2).add(e.clone().multiplyScalar(pl.u_offset)).setY(pl.eave_height)
    : d.clone().multiplyScalar(pl.eave_offset).add(e.clone().multiplyScalar(pl.u_offset)).setY(pl.eave_height)
  const toWorld = (u: number, v: number, lift = 0) => {
    const n = new THREE.Vector3().crossVectors(e, s).normalize()
    return origin
      .clone()
      .add(e.clone().multiplyScalar(u))
      .add(s.clone().multiplyScalar(pl.height_m - v))
      .add(n.multiplyScalar(lift))
  }
  const normal = new THREE.Vector3().crossVectors(e, s).normalize()
  return { e, s, origin, toWorld, normal, tilt }
}

function sunDirection(hour: number, month: number, lat: number) {
  // simple solar position: declination by month, hour angle by hour (solar time)
  const day = Math.round((month - 0.5) * 30.4)
  const decl = 23.44 * DEG * Math.sin(((360 / 365) * (day - 81)) * DEG)
  const ha = (hour - 12) * 15 * DEG
  const phi = lat * DEG
  const alt = Math.asin(Math.sin(phi) * Math.sin(decl) + Math.cos(phi) * Math.cos(decl) * Math.cos(ha))
  const azm = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(phi) - Math.tan(decl) * Math.cos(phi)) // 0 = south, + west
  // to world: X east, Z south
  const x = -Math.sin(azm) * Math.cos(alt) // west positive → −X
  const z = Math.cos(azm) * Math.cos(alt)
  const y = Math.sin(alt)
  return { dir: new THREE.Vector3(x, y, z), alt }
}

export function Scene3D({ project, onSaved }: { project: Project; onSaved?: (l: Layout) => void }) {
  const { t, lang } = useT()
  const toast = useToast()
  const wrap = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hour, setHour] = useState(12)
  const [month, setMonth] = useState(6)
  const [useTexture, setUseTexture] = useState(true)
  const [saving, setSaving] = useState(false)
  const stateRef = useRef<{ renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera; controls: OrbitControls; sun: THREE.DirectionalLight; home: () => void } | null>(null)
  const scene = useQuery({ queryKey: ['scene', project.id, project.updated_at, project.layouts.map((l) => l.updated_at).join()], queryFn: () => get<Scene>(`/api/projects/${project.id}/scene`) })
  const data = scene.data
  const lat = data?.site.lat ?? 43

  const sun = useMemo(() => sunDirection(hour, month, lat), [hour, month, lat])

  // build scene whenever data / texture choice changes
  useEffect(() => {
    const el = wrap.current
    const canvas = canvasRef.current
    if (!el || !canvas || !data) return
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, alpha: false })
    } catch {
      return
    }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.outputColorSpace = THREE.SRGBColorSpace
    const sc = new THREE.Scene()
    sc.background = new THREE.Color(0xdfe9f3)
    sc.fog = new THREE.Fog(0xdfe9f3, 120, 400)
    const cam = new THREE.PerspectiveCamera(42, 1, 0.1, 600)
    const controls = new OrbitControls(cam, canvas)
    controls.enableDamping = true
    controls.maxPolarAngle = Math.PI / 2 - 0.02
    controls.minDistance = 3

    const B = data.building
    const size = Math.max(B.width_m, B.depth_m, 12)
    // ground
    const ground = new THREE.Mesh(new THREE.CircleGeometry(size * 6, 64), new THREE.MeshStandardMaterial({ color: data.ground ? 0x6f8a4c : 0x8a9a6a, roughness: 1 }))
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    sc.add(ground)
    // building
    if (!data.ground) {
      const h = B.eave_height_m
      const wall = new THREE.Mesh(new THREE.BoxGeometry(B.width_m, h, B.depth_m), new THREE.MeshStandardMaterial({ color: new THREE.Color(B.colour[0] / 255, B.colour[1] / 255, B.colour[2] / 255), roughness: 0.9 }))
      wall.position.y = h / 2
      wall.castShadow = true
      wall.receiveShadow = true
      sc.add(wall)
      if (!data.flat) {
        // simple ridge "attic" wedge between the planes so the roof does not look hollow
        const ridge = B.ridge_height_m - h
        if (ridge > 0.05) {
          const shape = new THREE.Shape()
          shape.moveTo(-B.depth_m / 2, 0)
          shape.lineTo(B.depth_m / 2, 0)
          shape.lineTo(0, ridge)
          shape.closePath()
          const geo = new THREE.ExtrudeGeometry(shape, { depth: B.width_m, bevelEnabled: false })
          const attic = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xcfc9bd, roughness: 0.9 }))
          attic.rotation.y = Math.PI / 2
          attic.position.set(-B.width_m / 2, h, 0)
          attic.castShadow = true
          sc.add(attic)
        }
      }
    }
    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    const glass = new THREE.MeshPhysicalMaterial({ color: 0x0b1424, metalness: 0.1, roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.08, reflectivity: 0.9, envMapIntensity: 0.6 })
    const frameMat = new THREE.MeshStandardMaterial({ color: project.params?.visual && (project.params.visual as { frame?: string }).frame === 'silver' ? 0xb8bcc2 : 0x15161a, metalness: 0.6, roughness: 0.4 })
    const cellLineMat = new THREE.LineBasicMaterial({ color: 0x7c8694, transparent: true, opacity: 0.55 })
    const railMat = new THREE.MeshStandardMaterial({ color: 0xa8acb2, metalness: 0.7, roughness: 0.35 })

    for (const pl of data.planes) {
      const { toWorld, e, s, normal } = planeBasis(pl, data.flat || data.ground)
      // roof surface
      const poly = pl.roof_polygon.length >= 3 ? pl.roof_polygon : [[0, 0], [pl.width_m, 0], [pl.width_m, pl.height_m], [0, pl.height_m]]
      const rectGeo = new THREE.BufferGeometry()
      const corners = [toWorld(0, 0), toWorld(pl.width_m, 0), toWorld(pl.width_m, pl.height_m), toWorld(0, pl.height_m)]
      rectGeo.setAttribute('position', new THREE.Float32BufferAttribute(corners.flatMap((c) => [c.x, c.y, c.z]), 3))
      rectGeo.setAttribute('uv', new THREE.Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2))
      rectGeo.setIndex([0, 2, 1, 0, 3, 2])
      rectGeo.computeVertexNormals()
      const roofMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(pl.colour[0] / 255, pl.colour[1] / 255, pl.colour[2] / 255), roughness: 0.95, side: THREE.DoubleSide })
      if (useTexture && pl.texture) {
        loader.load(fileUrl(pl.texture), (tex) => {
          tex.colorSpace = THREE.SRGBColorSpace
          roofMat.map = tex
          roofMat.color.set(0xffffff)
          roofMat.needsUpdate = true
        })
      }
      const roof = new THREE.Mesh(rectGeo, roofMat)
      roof.receiveShadow = true
      roof.castShadow = true
      sc.add(roof)
      // usable outline
      if (pl.roof_polygon.length >= 3) {
        const pts = poly.map(([x, y]) => toWorld(x, y, 0.01))
        pts.push(pts[0])
        sc.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xc8322a })))
      }
      // obstacles: extruded boxes (0.6 m) around the polygon's bounding box
      for (const ob of pl.obstacles) {
        if (ob.length < 3) continue
        const xs = ob.map((p) => p[0])
        const ys = ob.map((p) => p[1])
        const x0 = Math.min(...xs)
        const x1 = Math.max(...xs)
        const y0 = Math.min(...ys)
        const y1 = Math.max(...ys)
        const geo = new THREE.BoxGeometry(x1 - x0, 0.6, y1 - y0)
        const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xb0574a, roughness: 0.9 }))
        const c = toWorld((x0 + x1) / 2, (y0 + y1) / 2, 0.3)
        m.position.copy(c)
        m.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(e, normal, s.clone().negate()))
        m.castShadow = true
        sc.add(m)
      }
      // modules
      const th = Math.max(0.03, pl.panel.thickness_m)
      const lift = pl.elevated ? 0.12 : 0.1 // rails
      const cols = pl.panel.cells % 6 === 0 || pl.panel.cells === 0 ? 6 : 5
      const rows = Math.max(1, Math.floor((pl.panel.cells || 108) / cols))
      const panelTilt = data.flat || data.ground ? pl.tilt * DEG : 0
      for (const p of pl.panels) {
        const g = new THREE.Group()
        const glassMesh = new THREE.Mesh(new THREE.BoxGeometry(p.w - 0.02, th * 0.4, p.h - 0.02), glass)
        glassMesh.position.y = th * 0.35
        glassMesh.castShadow = true
        glassMesh.receiveShadow = true
        g.add(glassMesh)
        const frame = new THREE.Mesh(new THREE.BoxGeometry(p.w, th, p.h), frameMat)
        frame.castShadow = true
        g.add(frame)
        // cell grid lines
        const pts: THREE.Vector3[] = []
        const cx = p.w > p.h ? rows : cols
        const cy = p.w > p.h ? cols : rows
        for (let i = 1; i < cx; i++) {
          const x = -p.w / 2 + (p.w * i) / cx
          pts.push(new THREE.Vector3(x, th * 0.56, -p.h / 2 + 0.02), new THREE.Vector3(x, th * 0.56, p.h / 2 - 0.02))
        }
        for (let j = 1; j < cy; j++) {
          const z = -p.h / 2 + (p.h * j) / cy
          pts.push(new THREE.Vector3(-p.w / 2 + 0.02, th * 0.56, z), new THREE.Vector3(p.w / 2 - 0.02, th * 0.56, z))
        }
        g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), cellLineMat))
        // placement: centre of the rect in plane coords, lifted by rails; rotate the group into the plane basis
        const centre = toWorld(p.x + p.w / 2, p.y + p.h / 2, lift + th / 2)
        g.position.copy(centre)
        const basis = new THREE.Matrix4().makeBasis(e, normal, s.clone().negate())
        g.quaternion.setFromRotationMatrix(basis)
        if (panelTilt > 0) {
          // flat roof / ground: tilt each module about its lower edge (facing the plane's azimuth)
          g.rotateX(-panelTilt)
          g.position.add(normal.clone().multiplyScalar((p.h / 2) * Math.sin(panelTilt)))
          // ballast feet
          const foot = new THREE.Mesh(new THREE.BoxGeometry(p.w * 0.9, 0.08, 0.3), railMat)
          foot.position.copy(toWorld(p.x + p.w / 2, p.y + p.h, 0.04))
          foot.quaternion.copy(new THREE.Quaternion().setFromRotationMatrix(basis))
          sc.add(foot)
        } else {
          // two rails under the module
          for (const f of [0.25, 0.75]) {
            const rail = new THREE.Mesh(new THREE.BoxGeometry(p.w + 0.02, 0.04, 0.04), railMat)
            rail.position.copy(toWorld(p.x + p.w / 2, p.y + p.h * f, lift / 2))
            rail.quaternion.copy(new THREE.Quaternion().setFromRotationMatrix(basis))
            sc.add(rail)
          }
        }
        sc.add(g)
      }
    }
    // lights
    const hemi = new THREE.HemisphereLight(0xffffff, 0x5c6b4a, 0.75)
    sc.add(hemi)
    const sunLight = new THREE.DirectionalLight(0xfff3e0, 2.2)
    sunLight.castShadow = true
    sunLight.shadow.mapSize.set(2048, 2048)
    const r = size * 1.6
    sunLight.shadow.camera.left = -r
    sunLight.shadow.camera.right = r
    sunLight.shadow.camera.top = r
    sunLight.shadow.camera.bottom = -r
    sunLight.shadow.camera.near = 1
    sunLight.shadow.camera.far = size * 8
    sunLight.shadow.bias = -0.0005
    sc.add(sunLight)
    sc.add(sunLight.target)
    // compass
    const compass = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), new THREE.Vector3(size * 0.9, 0.05, size * 0.9), 2.5, 0xc8322a, 0.8, 0.5)
    sc.add(compass)

    const home = () => {
      cam.position.set(size * 0.9, Math.max(B.ridge_height_m, 4) + size * 0.55, size * 1.3)
      controls.target.set(0, B.eave_height_m * 0.7, 0)
      controls.update()
    }
    home()
    const resize = () => {
      const w = el.clientWidth
      const h = Math.max(320, Math.min(window.innerHeight * 0.62, 640))
      renderer.setSize(w, h, false)
      cam.aspect = w / h
      cam.updateProjectionMatrix()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    let raf = 0
    const loop = () => {
      controls.update()
      renderer.render(sc, cam)
      raf = requestAnimationFrame(loop)
    }
    loop()
    stateRef.current = { renderer, scene: sc, camera: cam, controls, sun: sunLight, home }
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      sc.traverse((o) => {
        const m = o as THREE.Mesh
        if (m.geometry) m.geometry.dispose()
      })
      stateRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, useTexture])

  // sun position follows the sliders without rebuilding the scene
  useEffect(() => {
    const st = stateRef.current
    if (!st || !data) return
    const size = Math.max(data.building.width_m, data.building.depth_m, 12)
    const d = sun.dir.clone().multiplyScalar(size * 3)
    st.sun.position.copy(d)
    st.sun.target.position.set(0, 0, 0)
    st.sun.visible = sun.alt > 0.02
    st.sun.intensity = 0.6 + 1.8 * Math.max(0, Math.sin(sun.alt))
    const warm = Math.max(0, 1 - Math.sin(sun.alt) * 2)
    st.sun.color.setRGB(1, 0.95 - warm * 0.25, 0.88 - warm * 0.45)
    ;(st.scene.background as THREE.Color).setHSL(0.58, 0.45, sun.alt > 0.02 ? 0.82 : 0.35)
  }, [sun, data])

  const saveView = async () => {
    const st = stateRef.current
    if (!st) return
    setSaving(true)
    try {
      st.renderer.render(st.scene, st.camera)
      const png = st.renderer.domElement.toDataURL('image/png')
      const p = await post<Project>(`/api/projects/${project.id}/render3d`, { png })
      toast.push(t('scene_saved'), 'ok')
      if (onSaved && p.layouts[0]) onSaved(p.layouts[0])
    } catch (e) {
      toast.push(errMsg(e), 'bad')
    } finally {
      setSaving(false)
    }
  }

  const months = lang === 'bg' ? ['яну', 'фев', 'мар', 'апр', 'май', 'юни', 'юли', 'авг', 'сеп', 'окт', 'ное', 'дек'] : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

  return (
    <div className="flex flex-col gap-2" ref={wrap}>
      {scene.isLoading && (
        <p className="flex items-center gap-2 text-sm text-ink-3">
          <Spinner /> {t('scene_loading')}
        </p>
      )}
      {scene.isError && <p className="text-sm text-bad">{errMsg(scene.error)}</p>}
      {data && data.planes.length === 0 && <p className="py-10 text-center text-sm text-ink-3">{t('scene_empty')}</p>}
      <canvas ref={canvasRef} className={cx('w-full touch-none rounded', !data && 'hidden')} data-testid="scene-canvas" />
      {data && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-xs text-ink-3">{t('scene_hour')}</span>
            <input type="range" min={5} max={20} step={0.5} value={hour} onChange={(e) => setHour(Number(e.target.value))} className="w-32" />
            <span className="num w-10 text-xs">{fmtNum(Math.floor(hour), 0)}:{hour % 1 ? '30' : '00'}</span>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-xs text-ink-3">{t('scene_month')}</span>
            <input type="range" min={1} max={12} step={1} value={month} onChange={(e) => setMonth(Number(e.target.value))} className="w-28" />
            <span className="w-8 text-xs">{months[month - 1]}</span>
          </label>
          {data.planes.some((p) => p.texture) && <Toggle checked={useTexture} onChange={setUseTexture} label={t('scene_texture')} />}
          <span className="num text-xs text-ink-3">
            {data.modules} {t('modules_short')} · {fmtNum(data.kwp, 2)} kWp
          </span>
          <div className="ml-auto flex items-center gap-1">
            <button type="button" className="btn-quiet btn-sm" onClick={() => stateRef.current?.home()} title={t('scene_reset')} aria-label={t('scene_reset')}>
              <RotateCcw className="h-4 w-4" />
            </button>
            <button type="button" className="btn-ghost btn-sm" onClick={saveView} disabled={saving} data-testid="button-scene-save">
              {saving ? <Spinner /> : <Camera className="h-4 w-4" />} {t('scene_save_view')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
