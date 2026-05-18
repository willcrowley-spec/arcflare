import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/AppLayout'
import AnalysisPage from '@/pages/Analysis'
import OrganizationPage from '@/pages/Organization'
import ProcessesPage from '@/pages/Processes'
import DocumentsPage from './pages/Documents'
import DomainMapPage from '@/pages/Processes/DomainMap'
import RecommendationsPage from '@/pages/Recommendations'
import AgentsPage from '@/pages/Agents'
import AgentBuilderPage from '@/pages/AgentBuilder'
import PlatformDetailPage from '@/pages/Platforms'
import ArcbrainPage from '@/pages/Arcbrain'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/analysis" replace />} />
        <Route path="/analysis" element={<AnalysisPage />} />
        <Route path="/platforms/:connectionId" element={<PlatformDetailPage />} />
        <Route path="/organization" element={<OrganizationPage />} />
        <Route path="/processes" element={<ProcessesPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/processes/map" element={<Navigate to="/processes" replace />} />
        <Route path="/processes/:id/map" element={<DomainMapPage />} />
        <Route path="/recommendations" element={<RecommendationsPage />} />
        <Route path="/agent-builder/:runId" element={<AgentBuilderPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/arcbrain" element={<ArcbrainPage />} />
      </Route>
    </Routes>
  )
}
