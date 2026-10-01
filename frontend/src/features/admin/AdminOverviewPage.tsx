import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { useState } from "react";

import { Page, PageHeader } from "../../app/layout/Page";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Segmented } from "../../components/ui/Segmented";
import { Skeleton } from "../../components/ui/Skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/Tabs";
import { errorMessage } from "../../lib/api";
import { queries } from "../../lib/queries";
import { AIUsageTab } from "./AIUsageTab";
import { OverviewTab } from "./OverviewTab";
import { AmendmentsTab, ConflictsTab, DocumentsTab, FeedbackTab, UsersTab } from "./RecordTabs";

const WINDOWS = [7, 30, 90] as const;

/** Administrator's single page: usage, AI behaviour, every user, and all documents, amendments,
 *  conflicts and feedback. Read-only — actions happen on the work-queue pages it links to. */
export function AdminOverviewPage() {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);
  // Keep the previous window on screen while the new one loads (no skeleton flash, no layout jump).
  const stats = useQuery({ ...queries.stats(days), placeholderData: keepPreviousData });
  const overview = useQuery({ ...queries.overview(days), placeholderData: keepPreviousData });
  const o = overview.data;

  return (
    <Page title="Admin">
      <PageHeader
        eyebrow="Insights"
        title="Admin"
        description="Everything in one place: how Lumina is used, how the AI reached each answer, what every user did, and the state of documents, amendments, conflicts and feedback."
        actions={
          <Segmented
            label="Time window"
            value={days}
            onChange={setDays}
            options={WINDOWS.map((d) => [d, `${String(d)} days`] as const)}
          />
        }
      />
      {stats.isError || overview.isError ? (
        <ErrorNotice message={errorMessage(stats.error ?? overview.error)} />
      ) : !stats.data || !o ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <Tabs defaultValue="overview">
          <TabsList aria-label="Admin sections">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="ai">AI usage</TabsTrigger>
            <TabsTrigger value="users">Users ({o.users.length})</TabsTrigger>
            <TabsTrigger value="documents">Documents ({o.documents.length})</TabsTrigger>
            <TabsTrigger value="amendments">Amendments ({o.amendments.length})</TabsTrigger>
            <TabsTrigger value="conflicts">Conflicts ({o.conflicts.length})</TabsTrigger>
            <TabsTrigger value="feedback">Feedback ({o.feedback.length})</TabsTrigger>
          </TabsList>
          <div
            className={clsx(
              "pt-10 transition-opacity",
              (stats.isPlaceholderData || overview.isPlaceholderData) && "opacity-60",
            )}
          >
            <TabsContent value="overview">
              <OverviewTab stats={stats.data} />
            </TabsContent>
            <TabsContent value="ai">
              <AIUsageTab ai={o.ai} />
            </TabsContent>
            <TabsContent value="users">
              <UsersTab users={o.users} />
            </TabsContent>
            <TabsContent value="documents">
              <DocumentsTab documents={o.documents} />
            </TabsContent>
            <TabsContent value="amendments">
              <AmendmentsTab amendments={o.amendments} />
            </TabsContent>
            <TabsContent value="conflicts">
              <ConflictsTab conflicts={o.conflicts} />
            </TabsContent>
            <TabsContent value="feedback">
              <FeedbackTab feedback={o.feedback} />
            </TabsContent>
          </div>
        </Tabs>
      )}
    </Page>
  );
}
