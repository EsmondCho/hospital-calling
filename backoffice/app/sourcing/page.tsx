import { Suspense } from "react";

import { SourcingList } from "./sourcing-list";

// SourcingList reads pagination state via useSearchParams, which requires a
// Suspense boundary to prerender (Next.js 16 build constraint).
export default function SourcingPage() {
  return (
    <Suspense>
      <SourcingList />
    </Suspense>
  );
}
