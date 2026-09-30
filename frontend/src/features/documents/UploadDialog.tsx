import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Wand2 } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Input, Select, Textarea } from "../../components/ui/Field";
import { useToast } from "../../components/ui/Toast";
import { api, ApiError, errorMessage } from "../../lib/api";
import type { DocType, ExtractedMetadata, ReferenceData, UploadResult } from "../../lib/types";
import { DOC_TYPE_LABEL } from "./labels";

const ACCEPT = ".md,.markdown,.txt,.pdf,.docx,.html,.htm";

const schema = z
  .object({
    doc_code: z
      .string()
      .trim()
      .toUpperCase()
      .regex(/^[A-Z]{1,5}(-[A-Z0-9]{1,6}){1,3}$/, "Use a code like P-ICU-07, DG-01 or C-2026-09"),
    title: z.string().trim().min(3, "Enter the document title").max(300),
    doc_type: z.enum(["protocol", "drug_guideline", "circular", "sop", "external_reference"]),
    version_label: z
      .string()
      .trim()
      .regex(/^[A-Za-z0-9.-]{1,40}$/, "Letters, digits, '.' or '-' only"),
    effective_from: z.string().min(1, "Choose the date this version takes effect"),
    review_due: z.string().optional(),
    department_code: z.string().optional(),
    applies_to_all_branches: z.boolean(),
    branch_codes: z.array(z.string()),
    change_summary: z.string().max(2000).optional(),
  })
  .refine((v) => !v.review_due || v.review_due >= v.effective_from, {
    path: ["review_due"],
    message: "Review date cannot be before the effective date",
  })
  .refine((v) => v.applies_to_all_branches || v.branch_codes.length > 0, {
    path: ["branch_codes"],
    message: "Pick at least one branch, or make the document network-wide",
  });

type FormValues = z.infer<typeof schema>;

export interface UploadPreset {
  doc_code: string;
  title: string;
  doc_type: DocType;
  department_code?: string;
}

/** Upload a new document, or a new version of an existing one (preset locks its identity). */
export function UploadDialog({
  open,
  onOpenChange,
  preset,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preset?: UploadPreset;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      wide
      title={preset ? `Upload a new version of ${preset.doc_code}` : "Upload a document"}
      description="Accepted: Markdown, PDF (scanned pages are OCR'd), Word (.docx) or HTML. The upload stays a draft — clinicians never see it until it is approved."
    >
      {/* The dialog content unmounts when closed, so every opening starts with a fresh form. */}
      <UploadForm preset={preset} onClose={() => onOpenChange(false)} />
    </Dialog>
  );
}

function UploadForm({ preset, onClose }: { preset?: UploadPreset; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const reference = useQuery({
    queryKey: ["reference-data"],
    queryFn: () => api.get<ReferenceData>("/admin/reference-data"),
    staleTime: 5 * 60_000,
  });
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      doc_code: preset?.doc_code ?? "",
      title: preset?.title ?? "",
      doc_type: preset?.doc_type ?? "protocol",
      version_label: "",
      effective_from: "",
      review_due: "",
      department_code: preset?.department_code ?? "",
      applies_to_all_branches: true,
      branch_codes: [],
      change_summary: "",
    },
  });
  const { register, handleSubmit, formState, setValue, control } = form;
  const allBranches = useWatch({ control, name: "applies_to_all_branches" });

  const extract = useMutation({
    mutationFn: (f: File) => {
      const data = new FormData();
      data.append("file", f);
      return api.postForm<ExtractedMetadata>("/documents/extract-metadata", data);
    },
    onSuccess: (meta) => {
      const title = meta.title?.replace(/^[A-Z]{1,5}(-[A-Z0-9]{1,6}){1,3}\s+/, "");
      const candidates: [keyof FormValues, string | null | undefined, string][] = [
        ["doc_code", preset ? null : meta.doc_code, "code"],
        ["title", preset ? null : title, "title"],
        ["version_label", meta.version_label, "version"],
        ["effective_from", meta.effective_from, "effective date"],
        ["review_due", meta.review_due, "review date"],
      ];
      const filled: string[] = [];
      for (const [field, value, label] of candidates) {
        if (value) {
          setValue(field, value, { shouldValidate: true });
          filled.push(label);
        }
      }
      notify(
        filled.length ? `Filled ${filled.join(", ")} from the file` : "No details found in the file header",
        {
          tone: filled.length ? "success" : "info",
        },
      );
    },
    onError: (err) => notify("Could not read the file", { description: errorMessage(err), tone: "error" }),
  });

  const upload = useMutation({
    mutationFn: (values: FormValues) => {
      if (!file) throw new Error("Choose a file to upload");
      const data = new FormData();
      data.append("file", file);
      data.append("doc_code", values.doc_code);
      data.append("title", values.title);
      data.append("doc_type", values.doc_type);
      data.append("version_label", values.version_label);
      data.append("effective_from", values.effective_from);
      if (values.review_due) data.append("review_due", values.review_due);
      if (values.department_code) data.append("department_code", values.department_code);
      data.append("applies_to_all_branches", String(values.applies_to_all_branches));
      data.append("branch_codes", values.branch_codes.join(","));
      if (values.change_summary) data.append("change_summary", values.change_summary);
      return api.postForm<UploadResult>("/documents", data);
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["document", result.document_id] });
      notify("Uploaded — processing now", { description: "It stays a draft until an approver approves it." });
      onClose();
      void navigate(`/admin/documents/${result.document_id}`);
    },
  });

  const serverError = upload.error
    ? upload.error instanceof ApiError && Array.isArray(upload.error.details)
      ? (upload.error.details as string[]).join(" · ")
      : errorMessage(upload.error)
    : null;

  return (
    <form
      className="grid grid-cols-1 gap-4 sm:grid-cols-2"
      onSubmit={(e) => {
        if (!file) {
          e.preventDefault();
          setFileError("Choose a file to upload");
          return;
        }
        void handleSubmit((values) => upload.mutate(values))(e);
      }}
      noValidate
    >
      <div className="sm:col-span-2">
        <Field label="File" error={fileError ?? undefined}>
          {(props) => (
            <div className="flex flex-wrap items-center gap-2">
              <Input
                {...props}
                type="file"
                accept={ACCEPT}
                className="flex-1 py-2 file:mr-3 file:rounded-lg file:border-0 file:bg-accent-soft file:px-3 file:py-1.5 file:text-accent-text"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setFileError(null);
                }}
              />
              <Button
                variant="secondary"
                disabled={!file}
                loading={extract.isPending}
                onClick={() => file && extract.mutate(file)}
              >
                <Wand2 className="h-4 w-4" /> Read details from the file
              </Button>
            </div>
          )}
        </Field>
      </div>
      <Field label="Document code" error={formState.errors.doc_code?.message}>
        {(props) => <Input {...props} {...register("doc_code")} readOnly={!!preset} placeholder="P-ICU-07" />}
      </Field>
      <Field label="Type" error={formState.errors.doc_type?.message}>
        {(props) => (
          <Select {...props} {...register("doc_type")} disabled={!!preset}>
            {Object.entries(DOC_TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <div className="sm:col-span-2">
        <Field label="Title" error={formState.errors.title?.message}>
          {(props) => <Input {...props} {...register("title")} readOnly={!!preset} />}
        </Field>
      </div>
      <Field label="Version" error={formState.errors.version_label?.message}>
        {(props) => <Input {...props} {...register("version_label")} placeholder="4" />}
      </Field>
      <Field label="Department" hint="Conflicts are checked against documents in the same department.">
        {(props) => (
          <Select {...props} {...register("department_code")} disabled={!!preset}>
            <option value="">—</option>
            {reference.data?.departments.map((d) => (
              <option key={d.id} value={d.code}>
                {d.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Effective from" error={formState.errors.effective_from?.message}>
        {(props) => <Input {...props} type="date" {...register("effective_from")} />}
      </Field>
      <Field label="Review due" error={formState.errors.review_due?.message}>
        {(props) => <Input {...props} type="date" {...register("review_due")} />}
      </Field>
      {!preset ? (
        <fieldset className="sm:col-span-2">
          <legend className="mb-1.5 text-sm font-medium">Applies to</legend>
          <label className="flex min-h-11 items-center gap-2">
            <input
              type="checkbox"
              {...register("applies_to_all_branches")}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            All branches (network-wide)
          </label>
          {!allBranches ? (
            <div className="mt-1 flex flex-wrap gap-3">
              {reference.data?.branches.map((b) => (
                <label key={b.id} className="flex min-h-11 items-center gap-2">
                  <input
                    type="checkbox"
                    value={b.code}
                    {...register("branch_codes")}
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                  {b.name}
                </label>
              ))}
            </div>
          ) : null}
          {formState.errors.branch_codes ? (
            <p className="text-sm text-danger">{formState.errors.branch_codes.message}</p>
          ) : null}
        </fieldset>
      ) : null}
      <div className="sm:col-span-2">
        <Field label="What changed (optional)">
          {(props) => <Textarea {...props} rows={2} {...register("change_summary")} />}
        </Field>
      </div>
      {serverError ? (
        <div className="sm:col-span-2">
          <ErrorNotice title="Upload rejected" message={serverError} />
        </div>
      ) : null}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" loading={upload.isPending}>
          <FileUp className="h-4 w-4" /> Upload as draft
        </Button>
      </div>
    </form>
  );
}
