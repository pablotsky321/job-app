import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthGuard } from "./auth/AuthGuard";
import { CallbackView } from "./screens/auth/CallbackView";
import { OnboardingWizard } from "./screens/onboarding/OnboardingWizard";
import { VacancyListView } from "./screens/vacancies/VacancyListView";
import { VacancyDetailView } from "./screens/vacancies/VacancyDetailView";
import { ApplicationsListView } from "./screens/applications/ApplicationsListView";
import { ApplicationDetailView } from "./screens/applications/ApplicationDetailView";
import { SourcesView } from "./screens/sources/SourcesView";

function CatchAllPage() {
  return <div>TODO: Not Found</div>;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public route — OAuth callback */}
        <Route path="/callback" element={<CallbackView />} />

        {/* Protected routes — wrapped with AuthGuard */}
        <Route
          path="/onboarding/:step"
          element={
            <AuthGuard>
              <OnboardingWizard />
            </AuthGuard>
          }
        />
        <Route
          path="/vacancies"
          element={
            <AuthGuard>
              <VacancyListView />
            </AuthGuard>
          }
        />
        <Route
          path="/vacancies/:companyId/:vacancyId"
          element={
            <AuthGuard>
              <VacancyDetailView />
            </AuthGuard>
          }
        />
        <Route
          path="/applications"
          element={
            <AuthGuard>
              <ApplicationsListView />
            </AuthGuard>
          }
        />
        <Route
          path="/applications/:companyId/:vacancyId"
          element={
            <AuthGuard>
              <ApplicationDetailView />
            </AuthGuard>
          }
        />
        <Route
          path="/sources"
          element={
            <AuthGuard>
              <SourcesView />
            </AuthGuard>
          }
        />
        <Route
          path="*"
          element={
            <AuthGuard>
              <CatchAllPage />
            </AuthGuard>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
