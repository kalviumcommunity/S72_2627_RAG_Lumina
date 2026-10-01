import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitMerge, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { Page, PageHeader, SectionTitle } from "../../app/layout/Page";
import { useAuth } from "../../app/providers";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Input, Select, Textarea } from "../../components/ui/Field";
import { Skeleton } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { hasRole } from "../../lib/auth";
import { queries, queryKeys } from "../../lib/queries";
import type { Supersession } from "../../lib/types";
import { AmendmentList } from "./AmendmentList";

/** Amendment ("supersession") links: which circular or version replaces which clause, from when. */
export function SupersessionsPage() {
  const { session } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const links = useQuery(queries.supersessions());
  const pending = (links.data ?? []).filter((l) => !l.confirmed);
  const confirmed = (links.data ?? []).filter((l) => l.confirmed);

  return (
    <Page title="Amendments">
      <PageHeader
        eyebrow="Review"
        title="Amendments"
        description="When a circular amends a protocol clause, the old clause must stop appearing in answers. Links found automatically in uploaded circulars wait here until an approver confirms them."
        actions={
          hasRole(session?.user, "approver") ? (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> Add amendment link
            </Button>
          ) : undefined
        }
      />
      {links.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : links.isError ? (
        <ErrorNotice message={errorMessage(links.error)} />
      ) : (
        <div className="space-y-14">
          <section aria-label="Needs review">
            <SectionTitle>Needs review ({pending.length})</SectionTitle>
            {pending.length ? (
              <AmendmentList links={pending} />
            ) : (
              <EmptyState icon={<GitMerge className="h-6 w-6" />} title="No suggested amendments to review">
                New circulars are scanned for “replaces section …” wording when they are uploaded.
              </EmptyState>
            )}
          </section>
          <section aria-label="In force">
            <SectionTitle>In force ({confirmed.length})</SectionTitle>
            {confirmed.length ? (
              <AmendmentList links={confirmed} />
            ) : (
              <EmptyState title="No confirmed amendments yet" />
            )}
          </section>
        </div>
      )}
      <Dialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Add an amendment link"
        description="Record that a document version replaces a section (or all) of another document."
      >
        <CreateLinkForm onClose={() => setCreateOpen(false)} />
      </Dialog>
    </Page>
  );
}

function CreateLinkForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const docs = useQuery(queries.documents());
  const [sourceVersion, setSourceVersion] = useState("");
  const [target, setTarget] = useState("");
  const [section, setSection] = useState("");
  const [effective, setEffective] = useState("");
  const [note, setNote] = useState("");
  const [confirmNow, setConfirmNow] = useState(true);

  const versions = useMemo(
    () =>
      (docs.data ?? []).flatMap((d) =>
        d.versions.map((v) => ({
          id: v.id,
          label: `${d.doc_code} v${v.version_label} (${v.status})`,
          documentId: d.id,
          effective: v.effective_from,
        })),
      ),
    [docs.data],
  );
  const source = versions.find((v) => v.id === sourceVersion);

  const create = useMutation({
    mutationFn: () =>
      api.post<Supersession>("/supersessions", {
        source_version_id: sourceVersion,
        target_document_id: target,
        target_section_path: section.trim() || null,
        effective_from: effective || null,
        note: note.trim() || null,
        confirmed: confirmNow,
      }),
    onSuccess: () => {
      notify("Amendment link saved");
      void queryClient.invalidateQueries({ queryKey: queryKeys.supersessions });
      onClose();
    },
  });

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <Field label="Amending version (source)">
        {(props) => (
          <Select
            {...props}
            required
            value={sourceVersion}
            onChange={(e) => setSourceVersion(e.target.value)}
          >
            <option value="">Choose…</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Document it amends (target)">
        {(props) => (
          <Select {...props} required value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Choose…</option>
            {(docs.data ?? [])
              .filter((d) => d.id !== source?.documentId)
              .map((d) => (
                <option key={d.id} value={d.id}>
                  {d.doc_code} — {d.title}
                </option>
              ))}
          </Select>
        )}
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Section" hint="e.g. 4.2 — leave empty if the whole document is replaced.">
          {(props) => (
            <Input
              {...props}
              value={section}
              onChange={(e) => setSection(e.target.value)}
              placeholder="4.2"
            />
          )}
        </Field>
        <Field
          label="Effective from"
          hint={source ? `Defaults to the source's date (${source.effective}).` : undefined}
        >
          {(props) => (
            <Input {...props} type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />
          )}
        </Field>
      </div>
      <Field label="Note (optional)">
        {(props) => <Textarea {...props} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      <label className="flex min-h-11 items-center gap-3 text-sm">
        <input
          type="checkbox"
          checked={confirmNow}
          onChange={(e) => setConfirmNow(e.target.checked)}
          className="h-4 w-4 accent-black"
        />
        Confirm now (the amended section stops appearing in answers once in force)
      </label>
      {create.error ? <ErrorNotice title="Could not save" message={errorMessage(create.error)} /> : null}
      <div className="flex items-center justify-end gap-4">
        <Button variant="link" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={create.isPending} disabled={!sourceVersion || !target}>
          Save link
        </Button>
      </div>
    </form>
  );
}
