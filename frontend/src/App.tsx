import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminRoute } from './components/AdminRoute'
import { OnboardingRoute } from './components/OnboardingRoute'
import { ProtectedRoute } from './components/ProtectedRoute'
import { ScrollToTop } from './components/ScrollToTop'
import { AppLoadingScreen } from './components/ui/AppLoadingScreen'
import { DiaryPage } from './pages/DiaryPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { FriendsPage } from './pages/FriendsPage'
import { HomePage } from './pages/HomePage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { LoginPage } from './pages/LoginPage'
import { NewSchedulePage } from './pages/NewSchedulePage'
import { OnboardingPage } from './pages/OnboardingPage'
import { ProfilePage } from './pages/ProfilePage'
import { ReferencePage } from './pages/ReferencePage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { RestrictionsPage } from './pages/RestrictionsPage'
import { SettingsPage } from './pages/SettingsPage'
import { TeamDetailPage } from './pages/TeamDetailPage'
import { TeamRankingPage } from './pages/TeamRankingPage'
import { TeamsPage } from './pages/TeamsPage'
import { TrainingPartiesPage } from './pages/TrainingPartiesPage'
import { TrainingPartyDetailPage } from './pages/TrainingPartyDetailPage'
import { TrainingSessionPage } from './pages/TrainingSessionPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'
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
  return <AppLoadingScreen />
}

function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
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
      {/* Pathless layout route -- ProtectedRoute renders once (BottomNav
          included) and stays mounted across every navigation among these
          children, matched through its own <Outlet/>. See that
          component's docstring for why this replaced one <ProtectedRoute>
          wrapper per page. */}
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/schedule/new" element={<NewSchedulePage />} />
        <Route path="/training/:dayPlanId" element={<TrainingSessionPage />} />
        <Route path="/diary" element={<DiaryPage />} />
        <Route path="/restrictions" element={<RestrictionsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profile/:userId" element={<ProfilePage />} />
        <Route path="/friends" element={<FriendsPage />} />
        <Route path="/training-parties" element={<TrainingPartiesPage />} />
        <Route path="/training-parties/:partyId" element={<TrainingPartyDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/teams" element={<TeamsPage />} />
        <Route path="/teams/leaderboard" element={<TeamRankingPage />} />
        <Route path="/teams/:teamId" element={<TeamDetailPage />} />
        <Route
          path="/analytics"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <AnalyticsPage />
            </Suspense>
          }
        />
        <Route
          path="/coach"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <CoachPage />
            </Suspense>
          }
        />
        <Route path="/reference" element={<ReferencePage />} />
        <Route
          path="/reference/:articleId"
          element={
            <Suspense fallback={<RouteLoadingFallback />}>
              <ReferenceArticleDetailPage />
            </Suspense>
          }
        />
      </Route>
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
