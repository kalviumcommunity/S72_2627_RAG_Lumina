import type { DocType } from "../../lib/types";

export const DOC_TYPE_LABEL: Record<DocType, string> = {
  protocol: "Protocol",
  drug_guideline: "Drug guideline",
  circular: "Circular",
  sop: "SOP",
  external_reference: "External reference",
};
