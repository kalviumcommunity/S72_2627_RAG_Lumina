import { ButtonLink } from "../components/ui/Button";
import { Page } from "./layout/Page";
import { paths } from "./paths";

export function NotFoundPage() {
  return (
    <Page title="Page not found" width="narrow">
      <div className="py-16">
        <p className="mono-label text-muted">404</p>
        <h1 className="mt-3 text-section">Page not found</h1>
        <p className="mt-4 text-lead text-muted">The address may be old or mistyped.</p>
        <ButtonLink to={paths.ask} className="mt-8">
          Back to Ask
        </ButtonLink>
      </div>
    </Page>
  );
}
