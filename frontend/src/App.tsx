import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Loading } from './components/ui'
import { useAuth } from './lib/auth'
import CatalogPage from './pages/Catalog'
import DashboardPage from './pages/Dashboard'
import DeliveriesPage from './pages/Deliveries'
import LoginPage from './pages/Login'
import ProjectPage from './pages/Project'
import ProjectsPage from './pages/Projects'
import SettingsPage from './pages/Settings'

export default function App() {
  const { user, ready } = useAuth()
  if (!ready) return <Loading />
  if (!user) return <LoginPage />
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/deliveries" element={<DeliveriesPage />} />
        <Route path="/projects/:id" element={<ProjectPage />} />
        <Route path="/projects/:id/:step" element={<ProjectPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/catalog/:tab" element={<CatalogPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/:tab" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}
