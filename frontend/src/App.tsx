import { Navigate, Route, Routes } from 'react-router-dom'
import PortalLayout from './portal/components/PortalLayout'
import { PortalAuthProvider, PortalProtectedRoute } from './portal/auth'
import PortalHome from './portal/pages/Home'
import PortalLogin from './portal/pages/Login'
import PortalRegister from './portal/pages/Register'
import PortalSubmitRequest from './portal/pages/SubmitRequest'
import PortalMyRequests from './portal/pages/MyRequests'
import PortalRequestDetail from './portal/pages/RequestDetail'
import PortalTrackRequest from './portal/pages/TrackRequest'

export default function App() {
  return (
    <Routes>
      <Route
        path="/css-demo"
        element={
          <PortalAuthProvider>
            <PortalLayout />
          </PortalAuthProvider>
        }
      >
        <Route index element={<PortalHome />} />
        <Route path="login" element={<PortalLogin />} />
        <Route path="register" element={<PortalRegister />} />
        <Route
          path="submit"
          element={
            <PortalProtectedRoute>
              <PortalSubmitRequest />
            </PortalProtectedRoute>
          }
        />
        <Route
          path="requests"
          element={
            <PortalProtectedRoute>
              <PortalMyRequests />
            </PortalProtectedRoute>
          }
        />
        <Route
          path="requests/:ref"
          element={
            <PortalProtectedRoute>
              <PortalRequestDetail />
            </PortalProtectedRoute>
          }
        />
        <Route path="track" element={<PortalTrackRequest />} />
      </Route>
      <Route path="/" element={<Navigate to="/css-demo" replace />} />
      <Route path="*" element={<Navigate to="/css-demo" replace />} />
    </Routes>
  )
}
