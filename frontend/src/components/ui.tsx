/* Small UI kit: fields, modal, toasts, empty/loading states. */
import { AlertTriangle, CheckCircle2, Loader2, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

export function cx(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(' ')
}

export function Field({ label, hint, children, className, error }: { label?: ReactNode; hint?: ReactNode; children: ReactNode; className?: string; error?: string }) {
  return (
    <label className={cx('block min-w-0', className)}>
      {label && <span className="label">{label}</span>}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-bad">{error}</span>}
    </label>
  )
}

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx('input', className)} />
}

/** Numeric input that keeps a local string while typing and commits a number on blur/enter. */
export function NumInput({
  value,
  onChange,
  className,
  step,
  min,
  max,
  ...p
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> & { value: number | null | undefined; onChange: (v: number) => void }) {
  const [s, setS] = useState(value === null || value === undefined ? '' : String(value))
  const focused = useRef(false)
  useEffect(() => {
    if (!focused.current) setS(value === null || value === undefined ? '' : String(value))
  }, [value])
  const commit = () => {
    const v = parseFloat(s.replace(',', '.'))
    if (!Number.isNaN(v)) {
      let out = v
      if (min !== undefined && out < Number(min)) out = Number(min)
      if (max !== undefined && out > Number(max)) out = Number(max)
      onChange(out)
      setS(String(out))
    } else setS(value === null || value === undefined ? '' : String(value))
  }
  return (
    <input
      {...p}
      type="text"
      inputMode="decimal"
      step={step}
      value={s}
      onFocus={() => (focused.current = true)}
      onChange={(e) => setS(e.target.value)}
      onBlur={() => {
        focused.current = false
        commit()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
      }}
      className={cx('input num text-right', className)}
    />
  )
}

export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...p} className={cx('input appearance-none bg-no-repeat pr-8', className)} style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2712%27 height=%2712%27 viewBox=%270 0 24 24%27 fill=%27none%27 stroke=%27%23777%27 stroke-width=%272.5%27%3E%3Cpath d=%27m6 9 6 6 6-6%27/%3E%3C/svg%3E")', backgroundPosition: 'right 0.6rem center' }}>
      {children}
    </select>
  )
}

export function Textarea({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...p} className={cx('input h-auto min-h-[5rem] py-2 leading-snug', className)} />
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; disabled?: boolean }) {
  return (
    <label className={cx('inline-flex min-h-[44px] cursor-pointer select-none items-center gap-2 text-sm', disabled && 'opacity-50')}>
      <span
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault()
            if (!disabled) onChange(!checked)
          }
        }}
        onClick={() => !disabled && onChange(!checked)}
        className={cx('relative h-6 w-10 shrink-0 rounded-full transition', checked ? 'bg-ink' : 'bg-ink/20')}
      >
        <span className={cx('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition', checked ? 'left-[1.125rem]' : 'left-0.5')} />
      </span>
      {label}
    </label>
  )
}

export function Segmented<T extends string>({ value, onChange, options, size = 'md' }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; size?: 'sm' | 'md' }) {
  return (
    <div className="inline-flex max-w-full flex-wrap gap-1 rounded-md bg-surface-2 p-1" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            'rounded px-3 font-medium transition',
            size === 'sm' ? 'h-8 text-xs' : 'h-9 text-sm',
            value === o.value ? 'bg-surface text-ink shadow-card' : 'text-ink-2 hover:text-ink',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'ok' | 'warn' | 'bad' | 'sun'; children: ReactNode }) {
  const cls = {
    neutral: 'bg-surface-2 text-ink-2',
    ok: 'bg-ok/10 text-ok',
    warn: 'bg-warn/10 text-warn',
    bad: 'bg-bad/10 text-bad',
    sun: 'bg-sun-soft text-sun-ink',
  }[tone]
  return <span className={cx('badge', cls)}>{children}</span>
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx('h-4 w-4 animate-spin', className)} aria-hidden />
}

export function Loading({ label = '…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-ink-3" role="status">
      <Spinner /> {label}
    </div>
  )
}

export function Empty({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-start gap-3 border-dashed p-6 text-sm text-ink-2">
      <p>{title}</p>
      {children}
    </div>
  )
}

export function Warn({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded border border-warn/30 bg-warn/5 px-3 py-2 text-sm text-ink-2">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded border border-bad/30 bg-bad/5 px-3 py-2 text-sm text-bad" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0 break-words">{children}</div>
    </div>
  )
}

export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" className={cx('flex max-h-[92vh] w-full flex-col rounded-t-xl bg-surface shadow-pop sm:rounded-xl', wide ? 'sm:max-w-4xl' : 'sm:max-w-lg')}>
        <div className="flex items-center justify-between border-b border-line/10 px-4 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button type="button" className="btn-quiet btn-sm -mr-1.5 h-9 w-9 px-0" onClick={onClose} aria-label="close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">{children}</div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line/10 px-4 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Confirm({ open, onClose, onConfirm, title, text, danger }: { open: boolean; onClose: () => void; onConfirm: () => void; title: ReactNode; text?: ReactNode; danger?: boolean }) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            ✕
          </button>
          <button
            type="button"
            className={danger ? 'btn-danger' : 'btn-primary'}
            onClick={() => {
              onConfirm()
              onClose()
            }}
          >
            OK
          </button>
        </>
      }
    >
      <p className="text-sm text-ink-2">{text}</p>
    </Modal>
  )
}

// ------------------------------------------------------------------ toasts
interface Toast {
  id: number
  text: string
  tone: 'ok' | 'bad' | 'info'
}
const ToastCtx = createContext<{ push: (text: string, tone?: Toast['tone']) => void }>({ push: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    const id = Date.now() + Math.random()
    setItems((xs) => [...xs, { id, text, tone }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === 'bad' ? 6000 : 3000)
  }, [])
  const value = useMemo(() => ({ push }), [push])
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={cx(
              'pointer-events-auto flex max-w-md items-center gap-2 rounded-md px-3 py-2 text-sm shadow-pop',
              t.tone === 'bad' ? 'bg-bad text-white' : t.tone === 'ok' ? 'bg-ink text-white' : 'bg-surface text-ink',
            )}
          >
            {t.tone === 'ok' && <CheckCircle2 className="h-4 w-4" />}
            {t.tone === 'bad' && <AlertTriangle className="h-4 w-4" />}
            <span className="break-words">{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)

export function Stat({ label, value, sub }: { label: ReactNode; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-md bg-surface-2 px-3 py-2">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</div>
      <div className="num truncate text-lg font-semibold">{value}</div>
      {sub && <div className="text-xs text-ink-3">{sub}</div>}
    </div>
  )
}
