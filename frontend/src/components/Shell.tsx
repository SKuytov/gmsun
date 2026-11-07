import { BookOpen, FolderKanban, LayoutDashboard, LogOut, Settings2, Sun, Truck } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { useT } from '@/lib/i18n'
import { cx } from './ui'

export function Shell({ children }: { children: ReactNode }) {
  const { t, lang, setLang } = useT()
  const { user, logout } = useAuth()
  const items = [
    { to: '/dashboard', label: t('nav_dashboard'), icon: LayoutDashboard },
    { to: '/', label: t('nav_projects'), icon: FolderKanban, end: true },
    { to: '/deliveries', label: t('nav_deliveries'), icon: Truck },
    { to: '/catalog', label: t('nav_catalog'), icon: BookOpen },
    { to: '/settings', label: t('nav_settings'), icon: Settings2 },
  ]
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    cx(
      'flex items-center gap-2 rounded px-3 py-2 text-sm font-medium transition',
      isActive ? 'bg-sun-soft text-sun-ink' : 'text-ink-2 hover:bg-surface-2 hover:text-ink',
    )
  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col self-start overflow-y-auto border-r border-line/10 bg-surface px-3 py-4 md:flex">
        <div className="mb-6 flex items-center gap-2 px-2">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-ink text-sun">
            <Sun className="h-5 w-5" />
          </span>
          <div className="leading-tight">
            <div className="text-base font-bold tracking-tight">gmsun</div>
            <div className="text-xs text-ink-3">{t('app_tagline')}</div>
          </div>
        </div>
        <nav className="flex flex-col gap-1" aria-label="main">
          {items.map((it) => (
            <NavLink key={it.to} to={it.to} end={it.end} className={linkCls}>
              <it.icon className="h-4 w-4" /> {it.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-2 px-1 pt-6">
          <div className="flex items-center gap-1 text-xs">
            <button type="button" onClick={() => setLang('bg')} className={cx('rounded px-2 py-1 font-semibold', lang === 'bg' ? 'bg-ink text-white' : 'text-ink-3 hover:bg-surface-2')}>
              BG
            </button>
            <button type="button" onClick={() => setLang('en')} className={cx('rounded px-2 py-1 font-semibold', lang === 'en' ? 'bg-ink text-white' : 'text-ink-3 hover:bg-surface-2')}>
              EN
            </button>
          </div>
          <div className="truncate text-xs text-ink-3" title={user?.email}>
            {user?.name || user?.email}
          </div>
          <button type="button" className="btn-quiet btn-sm justify-start px-2" onClick={logout}>
            <LogOut className="h-4 w-4" /> {t('nav_logout')}
          </button>
        </div>
      </aside>

      {/* mobile top bar */}
      <header className="flex items-center justify-between border-b border-line/10 bg-surface px-4 py-2 md:hidden">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-ink text-sun">
            <Sun className="h-4 w-4" />
          </span>
          <span className="text-base font-bold">gmsun</span>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setLang(lang === 'bg' ? 'en' : 'bg')} className="btn-quiet btn-sm font-semibold">
            {lang.toUpperCase()}
          </button>
          <button type="button" className="btn-quiet btn-sm" onClick={logout} aria-label={t('nav_logout')}>
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      <main className="min-w-0 flex-1 px-4 pb-24 pt-4 md:px-8 md:pb-10 md:pt-6">{children}</main>

      {/* mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line/10 bg-surface md:hidden" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} aria-label="main mobile">
        {items.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.end}
            className={({ isActive }) => cx('flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 text-xs font-medium', isActive ? 'text-sun-ink' : 'text-ink-3')}
          >
            <it.icon className="h-5 w-5" /> {it.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
