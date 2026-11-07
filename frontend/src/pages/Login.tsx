import { Sun } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { ErrorBox, Field, Input, Spinner } from '@/components/ui'
import { errMsg, getServerUrl, isNative, setServerUrl } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useT } from '@/lib/i18n'

export default function LoginPage() {
  const { t, lang, setLang } = useT()
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [server, setServer] = useState('')
  const [showServer, setShowServer] = useState(isNative)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setServer(getServerUrl())
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      if (showServer) await setServerUrl(server.trim())
      await login(email.trim(), password)
    } catch (ex) {
      const m = errMsg(ex)
      setErr(/401|Incorrect|Грешен/i.test(m) ? t('login_failed') : m)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-bg px-4 py-10">
      <form onSubmit={submit} className="card w-full max-w-sm p-6" aria-labelledby="login-h">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-ink text-sun">
            <Sun className="h-6 w-6" />
          </span>
          <div>
            <h1 id="login-h" className="text-xl">
              gmsun
            </h1>
            <p className="text-xs text-ink-3">{t('app_tagline')}</p>
          </div>
          <button type="button" onClick={() => setLang(lang === 'bg' ? 'en' : 'bg')} className="btn-quiet btn-sm ml-auto font-semibold">
            {lang === 'bg' ? 'EN' : 'BG'}
          </button>
        </div>
        <div className="flex flex-col gap-3">
          <Field label={t('email')}>
            <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="input-email" />
          </Field>
          <Field label={t('password')}>
            <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="input-password" />
          </Field>
          {showServer ? (
            <Field label={t('server_url')} hint={t('server_url_hint')}>
              <Input type="url" placeholder="http://192.168.1.50" value={server} onChange={(e) => setServer(e.target.value)} data-testid="input-server" />
            </Field>
          ) : (
            <button type="button" className="self-start text-xs text-ink-3 underline-offset-2 hover:underline" onClick={() => setShowServer(true)}>
              {t('server_url')}
            </button>
          )}
          {err && <ErrorBox>{err}</ErrorBox>}
          <button type="submit" className="btn-primary mt-2 w-full" disabled={busy} data-testid="button-login">
            {busy && <Spinner />} {t('login_btn')}
          </button>
        </div>
      </form>
    </div>
  )
}
