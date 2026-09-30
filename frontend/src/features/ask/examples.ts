/** Demo questions — each one shows a different safety behaviour of the synthetic corpus. */
export const EXAMPLES: { question: string; shows: string }[] = [
  {
    question: "What is the heparin nomogram step for aPTT above 100?",
    shows: "Newest circular overrides the protocol",
  },
  { question: "When should aPTT be repeated after a heparin rate change?", shows: "Two documents disagree" },
  {
    question: "How soon should antibiotics be given for possible sepsis without shock?",
    shows: "Answer from a scanned PDF",
  },
  { question: "Does Tazocin need AMS approval?", shows: "Brand name → generic, table lookup" },
  {
    question: "Who do I call to activate the massive transfusion protocol?",
    shows: "Branch-specific procedure",
  },
  {
    question: "What heparin bolus should I give Mr Ramesh Kumar, 72 kg?",
    shows: "Patient-specific: refused, identifiers removed",
  },
];
