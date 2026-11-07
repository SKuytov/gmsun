/* HTTP client, token + server-URL storage (works in browser, sandboxed iframes and Capacitor Android). */
import { Capacitor } from '@capacitor/core'
import { Preferences } from '@capacitor/preferences'

export const isNative = Capacitor.isNativePlatform()

const mem: Record<string, string> = {}

async function storageGet(key: string): Promise<string | null> {
  if (isNative) {
    const { value } = await Preferences.get({ key })
    return value
  }
  try {
    return window.localStorage.getItem(key)
  } catch {
    return mem[key] ?? null
  }
}

async function storageSet(key: string, value: string | null): Promise<void> {
  if (isNative) {
    if (value === null) await Preferences.remove({ key })
    else await Preferences.set({ key, value })
    return
  }
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    if (value === null) delete mem[key]
    else mem[key] = value
  }
}

let token: string | null = null
let serverUrl = '' // '' => same origin (web deployment behind nginx)

export async function loadPersisted() {
  token = await storageGet('gmsun.token')
  serverUrl = (await storageGet('gmsun.server')) || (import.meta.env.VITE_API_URL as string | undefined) || ''
}

export function getToken() {
  return token
}
export async function setToken(t: string | null) {
  token = t
  await storageSet('gmsun.token', t)
}
export function getServerUrl() {
  return serverUrl
}
export async function setServerUrl(u: string) {
  serverUrl = u.replace(/\/+$/, '')
  await storageSet('gmsun.server', serverUrl)
}

export function apiUrl(path: string) {
  if (/^https?:\/\//.test(path)) return path
  return `${serverUrl}${path.startsWith('/') ? path : '/' + path}`
}

/** URL of a stored file (uploads/…, renders) – served by the API under /api/files/. */
export function fileUrl(rel: string | null | undefined) {
  if (!rel) return ''
  return apiUrl(`/api/files/${rel}`)
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : (detail as { detail?: string })?.detail || `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

type Listener = () => void
const unauthorizedListeners = new Set<Listener>()
export function onUnauthorized(fn: Listener) {
  unauthorizedListeners.add(fn)
  return () => unauthorizedListeners.delete(fn)
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; form?: FormData; raw?: boolean; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  const res = await fetch(apiUrl(path), { method: opts.method || (body ? 'POST' : 'GET'), headers, body, signal: opts.signal })
  if (res.status === 401) {
    unauthorizedListeners.forEach((fn) => fn())
  }
  if (!res.ok) {
    let detail: unknown = await res.text()
    try {
      detail = JSON.parse(detail as string)
    } catch {
      /* text */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  if (opts.raw) return (await res.blob()) as T
  return (await res.json()) as T
}

export const get = <T,>(path: string) => api<T>(path)
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body: body ?? {} })
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body })
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: 'PUT', body })
export const del = <T,>(path: string) => api<T>(path, { method: 'DELETE' })

/** Download a protected file (PDF/XLSX) – opens in a new tab in browsers, uses Share on Android. */
export async function downloadFile(path: string, filename: string) {
  const blob = await api<Blob>(path, { raw: true })
  if (isNative) {
    const { Filesystem, Directory } = await import('@capacitor/filesystem')
    const { Share } = await import('@capacitor/share')
    const b64 = await new Promise<string>((resolve) => {
      const r = new FileReader()
      r.onload = () => resolve((r.result as string).split(',')[1])
      r.readAsDataURL(blob)
    })
    const saved = await Filesystem.writeFile({ path: filename, data: b64, directory: Directory.Cache })
    await Share.share({ title: filename, url: saved.uri })
    return
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: unknown }
    if (d && typeof d === 'object' && 'detail' in d) {
      const det = d.detail
      if (typeof det === 'string') return det
      if (Array.isArray(det)) return det.map((x: { msg?: string; loc?: string[] }) => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ')
    }
    return e.message
  }
  if (e instanceof Error) return e.message
  return String(e)
}
