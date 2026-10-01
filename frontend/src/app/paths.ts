/**
 * Every in-app address, in one place. Pages link with these helpers instead of string literals, so
 * a route can move without hunting for hard-coded URLs.
 *
 * Information architecture (four sections, by role):
 *   Ask      /                          everyone
 *   Library  /library, /library/:id     author and above
 *   Review   /review/{amendments,conflicts,feedback}   author and above
 *   Admin    /admin, /admin/audit       administrator
 */
export const paths = {
  ask: "/",
  library: "/library",
  document: (documentId: string) => `/library/${documentId}`,
  review: "/review",
  amendments: "/review/amendments",
  conflicts: "/review/conflicts",
  feedback: "/review/feedback",
  admin: "/admin",
  audit: "/admin/audit",
  ssoCallback: "/auth/callback",
  apiDocs: "/docs",
} as const;

/** Addresses used before the restructure; they redirect so bookmarks and old links keep working. */
export const legacyRedirects: { from: string; to: string }[] = [
  { from: "/admin/documents", to: paths.library },
  { from: "/admin/supersessions", to: paths.amendments },
  { from: "/admin/conflicts", to: paths.conflicts },
  { from: "/admin/feedback", to: paths.feedback },
  { from: "/admin/overview", to: paths.admin },
  { from: "/admin/dashboard", to: paths.admin },
];
