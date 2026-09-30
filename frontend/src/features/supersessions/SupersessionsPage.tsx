import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitMerge, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { AdminPage, PageHeader } from "../../app/layout/AppShell";
import { useAuth } from "../../app/providers";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Input, Select, Textarea } from "../../components/ui/Field";
import { Skeleton } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { hasRole } from "../../lib/auth";
import type { DocumentSummary, Supersession } from "../../lib/types";
import { LinkTable } from "../documents/DocumentDetailPage";

/** Amendment ("supersession") links: which circular or version replaces which clause, from when. */
export function SupersessionsPage() {
  const { session } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const links = useQuery({
    queryKey: ["supersessions"],
    queryFn: () => api.get<Supersession[]>("/supersessions"),
  });
  const pending = (links.data ?? []).filter((l) => !l.confirmed);
  const confirmed = (links.data ?? []).filter((l) => l.confirmed);

  return (
    <AdminPage>
      <PageHeader
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
        <div className="space-y-6">
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
              Needs review ({pending.length})
            </h2>
            {pending.length ? (
              <LinkTable links={pending} />
            ) : (
              <EmptyState icon={<GitMerge className="h-7 w-7" />} title="No suggested amendments to review" />
            )}
          </section>
          <section>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
              In force ({confirmed.length})
            </h2>
            {confirmed.length ? (
              <LinkTable links={confirmed} />
            ) : (
              <EmptyState title="No confirmed amendments yet" />
            )}
          </section>
        </div>
      )}
      <CreateLinkDialog open={createOpen} onOpenChange={setCreateOpen} />
    </AdminPage>
  );
}

function CreateLinkDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add an amendment link"
      description="Record that a document version replaces a section (or all) of another document."
    >
      <CreateLinkForm onClose={() => onOpenChange(false)} />
    </Dialog>
  );
}

function CreateLinkForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api.get<DocumentSummary[]>("/documents") });
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
      void queryClient.invalidateQueries({ queryKey: ["supersessions"] });
      onClose();
    },
  });

  return (
    <form
      className="space-y-3"
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
      <Field label="Section" hint="e.g. 4.2 — leave empty if the whole document is replaced.">
        {(props) => (
          <Input {...props} value={section} onChange={(e) => setSection(e.target.value)} placeholder="4.2" />
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
      <Field label="Note (optional)">
        {(props) => <Textarea {...props} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      <label className="flex min-h-11 items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={confirmNow}
          onChange={(e) => setConfirmNow(e.target.checked)}
          className="h-4 w-4 accent-[var(--accent)]"
        />
        Confirm now (the amended section stops appearing in answers once in force)
      </label>
      {create.error ? <ErrorNotice title="Could not save" message={errorMessage(create.error)} /> : null}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={create.isPending} disabled={!sourceVersion || !target}>
          Save link
        </Button>
      </div>
    </form>
  );
}
