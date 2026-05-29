import type { ReactNode } from "react";

import { HospitalSelectionProvider } from "./selection-context";

// Wraps both the Hospitals list (`page.tsx`) and the hospital detail page
// (`[id]/page.tsx`). A shared segment layout does not remount on navigation,
// so the list's multi-select — held in the provider — survives a round trip
// into a hospital's detail page and back.
export default function HospitalsLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <HospitalSelectionProvider>{children}</HospitalSelectionProvider>;
}
