import { Navigate, Route, Routes } from 'react-router-dom'
import { OnboardingRoute } from './components/OnboardingRoute'
import { ProtectedRoute } from './components/ProtectedRoute'
import { HomePage } from './pages/HomePage'
import { LeaderboardPage } from './pages/LeaderboardPage'
import { LoginPage } from './pages/LoginPage'
import { NewSchedulePage } from './pages/NewSchedulePage'
import { OnboardingPage } from './pages/OnboardingPage'
import { ProfilePage } from './pages/ProfilePage'
import { ReferenceArticleDetailPage } from './pages/ReferenceArticleDetailPage'
import { ReferencePage } from './pages/ReferencePage'
import { RegisterPage } from './pages/RegisterPage'
import { SettingsPage } from './pages/SettingsPage'
import { TrainingSessionPage } from './pages/TrainingSessionPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
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
            <ReferenceArticleDetailPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
