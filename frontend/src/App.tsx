import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminRoute } from './components/AdminRoute'
import { OnboardingRoute } from './components/OnboardingRoute'
import { ProtectedRoute } from './components/ProtectedRoute'
import { ScrollToTop } from './components/ScrollToTop'
import { HomePage } from './pages/HomePage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { LoginPage } from './pages/LoginPage'
import { NewSchedulePage } from './pages/NewSchedulePage'
import { OnboardingPage } from './pages/OnboardingPage'
import { ProfilePage } from './pages/ProfilePage'
import { ReferencePage } from './pages/ReferencePage'
import { RegisterPage } from './pages/RegisterPage'
import { SettingsPage } from './pages/SettingsPage'
import { TeamDetailPage } from './pages/TeamDetailPage'
import { TeamsPage } from './pages/TeamsPage'
import { TrainingSessionPage } from './pages/TrainingSessionPage'
import { AdminExercisesPage } from './pages/admin/AdminExercisesPage'
import { AdminHomePage } from './pages/admin/AdminHomePage'
import { AdminSkillDetailPage } from './pages/admin/AdminSkillDetailPage'
import { AdminSkillsPage } from './pages/admin/AdminSkillsPage'
import { AdminUsersPage } from './pages/admin/AdminUsersPage'

// No route-based code-splitting elsewhere in the app yet (everything else
// is a static import) -- these two are singled out because they're the
// only places pulling in react-markdown (and its unified/remark/rehype
// chain), which would otherwise ship in the main bundle for every user,
// including the ones who never open the reference section or the admin
// panel.
const ReferenceArticleDetailPage = lazy(() =>
  import('./pages/ReferenceArticleDetailPage').then((module) => ({
    default: module.ReferenceArticleDetailPage,
  })),
)
const AdminReferenceArticlesPage = lazy(() =>
  import('./pages/admin/AdminReferenceArticlesPage').then((module) => ({
    default: module.AdminReferenceArticlesPage,
  })),
)
const PrivacyPage = lazy(() =>
  import('./pages/PrivacyPage').then((module) => ({ default: module.PrivacyPage })),
)
// Also lazy -- the only page pulling in recharts, kept out of the main
// bundle for everyone who never opens it, same reasoning as the
// react-markdown pages above.
const AnalyticsPage = lazy(() =>
  import('./pages/AnalyticsPage').then((module) => ({ default: module.AnalyticsPage })),
)
const CoachPage = lazy(() =>
  import('./pages/CoachPage').then((module) => ({ default: module.CoachPage })),
)

function RouteLoadingFallback() {
  return (
    <div className="flex min-h-svh items-center justify-center">
      <p className="text-sm text-text-secondary">Загрузка...</p>
    </div>
  )
}

function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/privacy"
        element={
          <Suspense fallback={<RouteLoadingFallback />}>
            <PrivacyPage />
          </Suspense>
        }
      />
      <Route
        path="/onboarding"
        element={
          <OnboardingRoute>
            <OnboardingPage />
          </OnboardingRoute>
        }
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <HomePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/schedule/new"
        element={
          <ProtectedRoute>
            <NewSchedulePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/training/:dayPlanId"
        element={
          <ProtectedRoute>
            <TrainingSessionPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <ProfilePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <SettingsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/leaderboard"
        element={
          <ProtectedRoute>
            <LeaderboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/teams"
        element={
          <ProtectedRoute>
            <TeamsPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/teams/:teamId"
        element={
          <ProtectedRoute>
            <TeamDetailPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/analytics"
        element={
          <ProtectedRoute>
            <Suspense fallback={<RouteLoadingFallback />}>
              <AnalyticsPage />
            </Suspense>
          </ProtectedRoute>
        }
      />
      <Route
        path="/coach"
        element={
          <ProtectedRoute>
            <Suspense fallback={<RouteLoadingFallback />}>
              <CoachPage />
            </Suspense>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reference"
        element={
          <ProtectedRoute>
            <ReferencePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reference/:articleId"
        element={
          <ProtectedRoute>
            <Suspense fallback={<RouteLoadingFallback />}>
              <ReferenceArticleDetailPage />
            </Suspense>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <AdminRoute>
            <AdminHomePage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/exercises"
        element={
          <AdminRoute>
            <AdminExercisesPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/skills"
        element={
          <AdminRoute>
            <AdminSkillsPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/skills/:skillId"
        element={
          <AdminRoute>
            <AdminSkillDetailPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/reference-articles"
        element={
          <AdminRoute>
            <Suspense fallback={<RouteLoadingFallback />}>
              <AdminReferenceArticlesPage />
            </Suspense>
          </AdminRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <AdminRoute>
            <AdminUsersPage />
          </AdminRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default App
