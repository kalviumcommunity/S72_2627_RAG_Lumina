import { ArrowRight } from "lucide-react";
import { Link } from "react-router";

import { paths } from "../../app/paths";
import { Badge } from "../../components/ui/Badge";
import { Table, Td, Th, Tr } from "../../components/ui/Table";
import { roleLabel } from "../../lib/auth";
import { formatDate, relativeTime } from "../../lib/format";
import type { Overview, Role } from "../../lib/types";
import { DOC_TYPE_LABEL } from "../documents/labels";

function Empty({ children }: { children: string }) {
  return <p className="text-sm text-muted">{children}</p>;
}

function ManageLink({ to, children }: { to: string; children: string }) {
  return (
    <p className="mt-6 text-sm">
      <Link to={to} className="inline-flex items-center gap-1.5">
        {children} <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </p>
  );
}

/** Activity of every user in the selected window. */
export function UsersTab({ users }: { users: Overview["users"] }) {
  if (!users.length) return <Empty>No users.</Empty>;
  return (
    <Table label="Usage per user">
      <thead>
        <tr>
          <Th>User</Th>
          <Th>Role</Th>
          <Th className="text-right">Questions</Th>
          <Th className="text-right">Answered</Th>
          <Th className="text-right">Escalated</Th>
          <Th className="text-right">Refused</Th>
          <Th className="text-right">Feedback</Th>
          <Th className="text-right">Uploads</Th>
          <Th className="text-right">Approvals</Th>
          <Th className="text-right">Reviews</Th>
          <Th>Last active</Th>
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <Tr key={u.user_id}>
            <Td className="min-w-44">
              <span className="font-medium">{u.name}</span>
              <span className="block text-micro text-muted">{u.branch ?? u.email}</span>
            </Td>
            <Td className="whitespace-nowrap">{roleLabel[u.role as Role]}</Td>
            <Td className="text-right font-medium tabular-nums">{u.questions}</Td>
            <Td className="text-right tabular-nums">{u.answered + u.partial}</Td>
            <Td className="text-right tabular-nums">{u.abstained - u.refused_high_risk}</Td>
            <Td className="text-right tabular-nums">{u.refused_high_risk}</Td>
            <Td className="text-right tabular-nums">{u.feedback_given}</Td>
            <Td className="text-right tabular-nums">{u.uploads}</Td>
            <Td className="text-right tabular-nums">{u.approvals}</Td>
            <Td className="text-right tabular-nums">{u.reviews}</Td>
            <Td className="whitespace-nowrap text-muted">
              {u.last_active ? relativeTime(u.last_active) : "—"}
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}

export function DocumentsTab({ documents }: { documents: Overview["documents"] }) {
  if (!documents.length) return <Empty>No documents yet.</Empty>;
  return (
    <>
      <Table label="Documents">
        <thead>
          <tr>
            <Th>Document</Th>
            <Th>Type</Th>
            <Th>Owner</Th>
            <Th>In force</Th>
            <Th className="text-right">Drafts</Th>
            <Th>Review due</Th>
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <Tr key={d.id}>
              <Td>
                <Link to={paths.document(d.id)} className="font-mono">
                  {d.doc_code}
                </Link>
                <span className="block">{d.title}</span>
              </Td>
              <Td className="whitespace-nowrap">
                {(DOC_TYPE_LABEL as Record<string, string>)[d.doc_type] ?? d.doc_type}
              </Td>
              <Td className="whitespace-nowrap">{d.owner ?? "—"}</Td>
              <Td className="whitespace-nowrap">
                {d.current_version
                  ? `v${d.current_version} since ${formatDate(d.effective_from)}`
                  : "none yet"}
              </Td>
              <Td className="text-right tabular-nums">{d.drafts || "—"}</Td>
              <Td className={d.review_overdue ? "whitespace-nowrap text-error" : "whitespace-nowrap"}>
                {formatDate(d.review_due)}
                {d.review_overdue ? " (overdue)" : ""}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      <ManageLink to={paths.library}>Upload or approve documents</ManageLink>
    </>
  );
}

export function AmendmentsTab({ amendments }: { amendments: Overview["amendments"] }) {
  if (!amendments.length) return <Empty>No amendments recorded.</Empty>;
  return (
    <>
      <Table label="Amendments">
        <thead>
          <tr>
            <Th>Amending document</Th>
            <Th>Replaces</Th>
            <Th>From</Th>
            <Th>Status</Th>
            <Th>Evidence found in the text</Th>
          </tr>
        </thead>
        <tbody>
          {amendments.map((a) => (
            <Tr key={a.id}>
              <Td className="whitespace-nowrap font-medium">
                {a.source}
                {a.source_status !== "approved" ? (
                  <span className="block text-micro text-muted">{a.source_status}</span>
                ) : null}
              </Td>
              <Td className="whitespace-nowrap">{a.target}</Td>
              <Td className="whitespace-nowrap">{formatDate(a.effective_from)}</Td>
              <Td className="whitespace-nowrap">
                {a.confirmed ? (
                  <Badge tone="success">In force</Badge>
                ) : (
                  <Badge tone="amber">Needs review</Badge>
                )}
              </Td>
              <Td className="italic text-muted">{a.evidence ? `“${a.evidence}”` : "added manually"}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      <ManageLink to={paths.amendments}>Confirm or reject amendments</ManageLink>
    </>
  );
}

const DETECTED: Record<string, string> = {
  query: "while answering",
  ingest: "at approval",
  user: "by a user",
};

export function ConflictsTab({ conflicts }: { conflicts: Overview["conflicts"] }) {
  if (!conflicts.length) return <Empty>No conflicts found between current documents.</Empty>;
  return (
    <>
      <Table label="Conflicts">
        <thead>
          <tr>
            <Th>Between</Th>
            <Th>What differs</Th>
            <Th>Status</Th>
            <Th>Found</Th>
            <Th>Owner</Th>
          </tr>
        </thead>
        <tbody>
          {conflicts.map((c) => (
            <Tr key={c.id}>
              <Td className="whitespace-nowrap font-medium">
                {c.a}
                <span className="block text-muted">vs {c.b}</span>
              </Td>
              <Td className="min-w-72">{c.description}</Td>
              <Td className="whitespace-nowrap capitalize">{c.status}</Td>
              <Td className="whitespace-nowrap text-muted">
                {DETECTED[c.detected_by] ?? c.detected_by}, {relativeTime(c.created_at)}
              </Td>
              <Td className="whitespace-nowrap">{c.owner ?? "—"}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      <ManageLink to={paths.conflicts}>Resolve conflicts</ManageLink>
    </>
  );
}

const KIND: Record<string, string> = {
  wrong: "Wrong",
  outdated: "Outdated",
  unhelpful: "Not helpful",
  helpful: "Helpful",
};

export function FeedbackTab({ feedback }: { feedback: Overview["feedback"] }) {
  if (!feedback.length) return <Empty>No feedback yet.</Empty>;
  return (
    <>
      <Table label="Feedback">
        <thead>
          <tr>
            <Th>When</Th>
            <Th>From</Th>
            <Th>Rating</Th>
            <Th>Question</Th>
            <Th>Comment</Th>
            <Th>Status</Th>
            <Th>Sent to</Th>
          </tr>
        </thead>
        <tbody>
          {feedback.map((f) => (
            <Tr key={f.id}>
              <Td className="whitespace-nowrap text-muted">{relativeTime(f.created_at)}</Td>
              <Td className="whitespace-nowrap">{f.reporter ?? "—"}</Td>
              <Td className="whitespace-nowrap">{KIND[f.kind] ?? f.kind}</Td>
              <Td className="min-w-56">{f.question}</Td>
              <Td className="min-w-40 text-muted">{f.comment ?? "—"}</Td>
              <Td className="whitespace-nowrap capitalize">{f.kind === "helpful" ? "—" : f.status}</Td>
              <Td className="whitespace-nowrap">{f.routed_to ?? "—"}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      <ManageLink to={paths.feedback}>Answer feedback</ManageLink>
    </>
  );
}
