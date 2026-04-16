import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import AnalysisPage from '@/pages/Analysis'
import OrganizationPage from '@/pages/Organization'
import ProcessesPage from '@/pages/Processes'
import ProcessMapPage from '@/pages/Processes/ProcessMap'
import RecommendationsPage from '@/pages/Recommendations'
import AgentsPage from '@/pages/Agents'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/analysis" replace />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/organization" element={<OrganizationPage />} />
        <Route path="/processes" element={<ProcessesPage />} />
        <Route path="/processes/map" element={<ProcessMapPage />} />
        <Route path="/recommendations" element={<RecommendationsPage />} />
        <Route path="/agents" element={<AgentsPage />} />
      </Route>
    </Routes>
  )
}
