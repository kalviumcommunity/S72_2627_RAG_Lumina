import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router";

import { AuditPage } from "../features/audit/AuditPage";
import { LoginPage } from "../features/auth/LoginPage";
import { AskPage } from "../features/ask/AskPage";
import { ConflictsPage } from "../features/conflicts/ConflictsPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { DocumentDetailPage } from "../features/documents/DocumentDetailPage";
import { DocumentsPage } from "../features/documents/DocumentsPage";
import { FeedbackPage } from "../features/feedback/FeedbackPage";
import { SupersessionsPage } from "../features/supersessions/SupersessionsPage";
import { AdminPage, AppShell } from "./layout/AppShell";
import { useAuth } from "./providers";
import { RequireRole } from "./RequireRole";

function NotFound() {
  return (
    <AdminPage>
      <div className="mx-auto max-w-md text-center">
        <h1 className="text-lg font-semibold">Page not found</h1>
        <Link to="/" className="mt-2 inline-block text-sm font-medium">
          Back to Ask
        </Link>
      </div>
    </AdminPage>
  );
}

export function App() {
  const { session } = useAuth();
  return (
    <BrowserRouter>
      {session ? (
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<AskPage />} />
            <Route path="admin" element={<RequireRole role="author" />}>
              <Route index element={<Navigate to="documents" replace />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="documents/:documentId" element={<DocumentDetailPage />} />
              <Route path="supersessions" element={<SupersessionsPage />} />
              <Route path="conflicts" element={<ConflictsPage />} />
              <Route path="feedback" element={<FeedbackPage />} />
              <Route element={<RequireRole role="admin" />}>
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="audit" element={<AuditPage />} />
              </Route>
            </Route>
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      ) : (
        <Routes>
          <Route path="*" element={<LoginPage />} />
        </Routes>
      )}
    </BrowserRouter>
  );
}
