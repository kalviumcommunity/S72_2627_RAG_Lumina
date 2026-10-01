import { BrowserRouter, Route, Routes } from "react-router";

import { LoginPage } from "../features/auth/LoginPage";
import { ErrorBoundary } from "./ErrorBoundary";
import { useAuth } from "./providers";
import { AppRoutes } from "./routes";

/** Signed out: every address shows sign-in (and is kept, so a deep link opens after signing in). */
export function App() {
  const { session } = useAuth();
  return (
    <BrowserRouter>
      <ErrorBoundary>
        {session ? (
          <AppRoutes />
        ) : (
          <Routes>
            <Route path="*" element={<LoginPage />} />
          </Routes>
        )}
      </ErrorBoundary>
    </BrowserRouter>
  );
}
