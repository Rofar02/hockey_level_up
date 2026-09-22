import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminRoute } from './components/AdminRoute'
import { OnboardingRoute } from './components/OnboardingRoute'
import { ProtectedRoute } from './components/ProtectedRoute'
import { ScrollToTop } from './components/ScrollToTop'
import { AppLoadingScreen } from './components/ui/AppLoadingScreen'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'

// Kept as static imports, unlike every other page below -- these are the
// actual first paint for a logged-out visitor (there's no auth check ahead
// of them to cover a lazy chunk's own loading flicker with, the way
// ProtectedRoute/AdminRoute/OnboardingRoute's own Suspense boundaries do
// for everything behind a login), and they're small enough (plain forms)
// that splitting them out barely moves the main bundle either way.

// Every page below (except the five auth forms above) used to be a static
// import -- all ~35 of them landing in one main JS chunk regardless of
// which single page a given visit actually needs. Suspense for these lives
// one level up, in ProtectedRoute/AdminRoute/OnboardingRoute themselves
// (wrapping Outlet/children there), not per-route here -- see
// ProtectedRoute's own comment for why that placement specifically matters
// (BottomNav must not unmount while a page chunk loads).
const HomePage = lazy(() => import('./pages/HomePage').then((m) => ({ default: m.HomePage })))
const NewSchedulePage = lazy(() =>
  import('./pages/NewSchedulePage').then((m) => ({ default: m.NewSchedulePage })),
)
const TrainingSessionPage = lazy(() =>
  import('./pages/TrainingSessionPage').then((m) => ({ default: m.TrainingSessionPage })),
)
const TrainingDiaryPage = lazy(() =>
  import('./pages/TrainingDiaryPage').then((m) => ({ default: m.TrainingDiaryPage })),
)
const DiaryPage = lazy(() => import('./pages/DiaryPage').then((m) => ({ default: m.DiaryPage })))
const MorePage = lazy(() => import('./pages/MorePage').then((m) => ({ default: m.MorePage })))
const RestrictionsPage = lazy(() =>
  import('./pages/RestrictionsPage').then((m) => ({ default: m.RestrictionsPage })),
)
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const FriendsPage = lazy(() => import('./pages/FriendsPage').then((m) => ({ default: m.FriendsPage })))
const TrainingPartiesPage = lazy(() =>
  import('./pages/TrainingPartiesPage').then((m) => ({ default: m.TrainingPartiesPage })),
)
const TrainingPartyDetailPage = lazy(() =>
  import('./pages/TrainingPartyDetailPage').then((m) => ({ default: m.TrainingPartyDetailPage })),
)
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const SettingsProfilePage = lazy(() =>
  import('./pages/SettingsProfilePage').then((m) => ({ default: m.SettingsProfilePage })),
)
const SettingsEquipmentPage = lazy(() =>
  import('./pages/SettingsEquipmentPage').then((m) => ({ default: m.SettingsEquipmentPage })),
)
const SettingsTrainingPage = lazy(() =>
  import('./pages/SettingsTrainingPage').then((m) => ({ default: m.SettingsTrainingPage })),
)
const SettingsAssessmentsPage = lazy(() =>
  import('./pages/SettingsAssessmentsPage').then((m) => ({ default: m.SettingsAssessmentsPage })),
)
const SettingsNotificationsPage = lazy(() =>
  import('./pages/SettingsNotificationsPage').then((m) => ({
    default: m.SettingsNotificationsPage,
  })),
)
const SettingsAccountPage = lazy(() =>
  import('./pages/SettingsAccountPage').then((m) => ({ default: m.SettingsAccountPage })),
)
const LeaderboardPage = lazy(() =>
  import('./pages/LeaderboardPage').then((m) => ({ default: m.LeaderboardPage })),
)
const TeamsPage = lazy(() => import('./pages/TeamsPage').then((m) => ({ default: m.TeamsPage })))
const TeamRankingPage = lazy(() =>
  import('./pages/TeamRankingPage').then((m) => ({ default: m.TeamRankingPage })),
)
const TeamDetailPage = lazy(() =>
  import('./pages/TeamDetailPage').then((m) => ({ default: m.TeamDetailPage })),
)
// Also lazy -- the only page pulling in recharts, kept out of the main
// bundle for everyone who never opens it.
const AnalyticsPage = lazy(() =>
  import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)
const CoachPage = lazy(() => import('./pages/CoachPage').then((m) => ({ default: m.CoachPage })))
const ReferencePage = lazy(() =>
  import('./pages/ReferencePage').then((m) => ({ default: m.ReferencePage })),
)
const ExerciseCatalogPage = lazy(() =>
  import('./pages/ExerciseCatalogPage').then((m) => ({ default: m.ExerciseCatalogPage })),
)
const QuestsPage = lazy(() => import('./pages/QuestsPage').then((m) => ({ default: m.QuestsPage })))
// Pulls in react-markdown (and its unified/remark/rehype chain) -- kept out
// of the main bundle for everyone who never opens the reference section.
const ReferenceArticleDetailPage = lazy(() =>
  import('./pages/ReferenceArticleDetailPage').then((m) => ({
    default: m.ReferenceArticleDetailPage,
  })),
)
const PrivacyPage = lazy(() => import('./pages/PrivacyPage').then((m) => ({ default: m.PrivacyPage })))
const OnboardingPage = lazy(() =>
  import('./pages/OnboardingPage').then((m) => ({ default: m.OnboardingPage })),
)

const AdminHomePage = lazy(() =>
  import('./pages/admin/AdminHomePage').then((m) => ({ default: m.AdminHomePage })),
)
const AdminExercisesPage = lazy(() =>
  import('./pages/admin/AdminExercisesPage').then((m) => ({ default: m.AdminExercisesPage })),
)
const AdminSkillsPage = lazy(() =>
  import('./pages/admin/AdminSkillsPage').then((m) => ({ default: m.AdminSkillsPage })),
)
const AdminSkillDetailPage = lazy(() =>
  import('./pages/admin/AdminSkillDetailPage').then((m) => ({ default: m.AdminSkillDetailPage })),
)
const AdminUsersPage = lazy(() =>
  import('./pages/admin/AdminUsersPage').then((m) => ({ default: m.AdminUsersPage })),
)
// Pulls in react-markdown, same reasoning as ReferenceArticleDetailPage above.
const AdminReferenceArticlesPage = lazy(() =>
  import('./pages/admin/AdminReferenceArticlesPage').then((m) => ({
    default: m.AdminReferenceArticlesPage,
  })),
)

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
      {/* No auth check ahead of this one (unlike everything gated by
          ProtectedRoute/AdminRoute/OnboardingRoute below), so it needs its
          own Suspense boundary rather than inheriting one from a layout. */}
      <Route
        path="/privacy"
        element={
          <Suspense fallback={<AppLoadingScreen />}>
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
        <Route path="/training/:dayPlanId/diary" element={<TrainingDiaryPage />} />
        <Route path="/diary" element={<DiaryPage />} />
        <Route path="/more" element={<MorePage />} />
        <Route path="/restrictions" element={<RestrictionsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profile/:userId" element={<ProfilePage />} />
        <Route path="/friends" element={<FriendsPage />} />
        <Route path="/training-parties" element={<TrainingPartiesPage />} />
        <Route path="/training-parties/:partyId" element={<TrainingPartyDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/profile" element={<SettingsProfilePage />} />
        <Route path="/settings/equipment" element={<SettingsEquipmentPage />} />
        <Route path="/settings/training" element={<SettingsTrainingPage />} />
        <Route path="/settings/assessments" element={<SettingsAssessmentsPage />} />
        <Route path="/settings/notifications" element={<SettingsNotificationsPage />} />
        <Route path="/settings/account" element={<SettingsAccountPage />} />
        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/teams" element={<TeamsPage />} />
        <Route path="/teams/leaderboard" element={<TeamRankingPage />} />
        <Route path="/teams/:teamId" element={<TeamDetailPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/coach" element={<CoachPage />} />
        <Route path="/reference" element={<ReferencePage />} />
        <Route path="/exercise-catalog" element={<ExerciseCatalogPage />} />
        <Route path="/quests" element={<QuestsPage />} />
        <Route path="/reference/:articleId" element={<ReferenceArticleDetailPage />} />
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
            <AdminReferenceArticlesPage />
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
