/** Demo questions — each one shows a different safety behaviour of the synthetic corpus. */
export const EXAMPLES: { question: string; tag: string; shows: string }[] = [
  {
    question: "What is the heparin nomogram step for aPTT above 100?",
    tag: "Amendment",
    shows: "The newest circular overrides the protocol clause",
  },
  {
    question: "When should aPTT be repeated after a heparin rate change?",
    tag: "Conflict",
    shows: "Two approved documents disagree — both are shown",
  },
  {
    question: "How soon should antibiotics be given for possible sepsis without shock?",
    tag: "Scanned PDF",
    shows: "Answered from an OCR-read circular",
  },
  {
    question: "Does Tazocin need AMS approval?",
    tag: "Brand name",
    shows: "Brand name mapped to the generic, answered from a table",
  },
  {
    question: "Who do I call to activate the massive transfusion protocol?",
    tag: "Branch",
    shows: "Your branch's own procedure comes first",
  },
  {
    question: "What heparin bolus should I give Mr Ramesh Kumar, 72 kg?",
    tag: "Refusal",
    shows: "Patient-specific: refused, identifiers removed",
  },
];
