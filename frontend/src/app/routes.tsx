import { lazy } from "react";
import { Navigate, Route, Routes, useParams } from "react-router";

import { AskPage } from "../features/ask/AskPage";
import { NotFoundPage } from "./NotFoundPage";
import { AppShell } from "./layout/AppShell";
import { SectionLayout } from "./layout/SectionLayout";
import { legacyRedirects, paths } from "./paths";
import { RequireRole } from "./RequireRole";

// Ask is what every user opens first, so it ships in the main bundle; the staff and admin
// sections (and the PDF viewer they pull in) load on demand.
const DocumentsPage = lazy(() =>
  import("../features/documents/DocumentsPage").then((m) => ({ default: m.DocumentsPage })),
);
const DocumentDetailPage = lazy(() =>
  import("../features/documents/DocumentDetailPage").then((m) => ({ default: m.DocumentDetailPage })),
);
const SupersessionsPage = lazy(() =>
  import("../features/supersessions/SupersessionsPage").then((m) => ({ default: m.SupersessionsPage })),
);
const ConflictsPage = lazy(() =>
  import("../features/conflicts/ConflictsPage").then((m) => ({ default: m.ConflictsPage })),
);
const FeedbackPage = lazy(() =>
  import("../features/feedback/FeedbackPage").then((m) => ({ default: m.FeedbackPage })),
);
const AdminOverviewPage = lazy(() =>
  import("../features/admin/AdminOverviewPage").then((m) => ({ default: m.AdminOverviewPage })),
);
const AuditPage = lazy(() => import("../features/audit/AuditPage").then((m) => ({ default: m.AuditPage })));

function LegacyDocumentRedirect() {
  const { documentId = "" } = useParams();
  return <Navigate to={paths.document(documentId)} replace />;
}

/** Signed-in route tree. Role gates wrap each section; the API enforces the same rules. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<AskPage />} />
        {/* Landing page after hospital SSO sign-in (the token is read by AuthProvider). */}
        <Route path="auth/callback" element={<Navigate to={paths.ask} replace />} />

        <Route element={<RequireRole role="author" />}>
          <Route path="library" element={<DocumentsPage />} />
          <Route path="library/:documentId" element={<DocumentDetailPage />} />
          <Route path="review" element={<SectionLayout section="review" />}>
            <Route index element={<Navigate to={paths.amendments} replace />} />
            <Route path="amendments" element={<SupersessionsPage />} />
            <Route path="conflicts" element={<ConflictsPage />} />
            <Route path="feedback" element={<FeedbackPage />} />
          </Route>
        </Route>

        <Route path="admin" element={<RequireRole role="admin" />}>
          <Route element={<SectionLayout section="admin" />}>
            <Route index element={<AdminOverviewPage />} />
            <Route path="audit" element={<AuditPage />} />
          </Route>
        </Route>

        {legacyRedirects.map(({ from, to }) => (
          <Route key={from} path={from.slice(1)} element={<Navigate to={to} replace />} />
        ))}
        <Route path="admin/documents/:documentId" element={<LegacyDocumentRedirect />} />

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
