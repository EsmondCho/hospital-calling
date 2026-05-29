import { Suspense } from "react";

import { CallsList } from "./calls-list";

// CallsList reads filter/pagination state via useSearchParams, which requires
// a Suspense boundary to prerender (Next.js 16 build constraint).
export default function CallsPage() {
  return (
    <Suspense>
      <CallsList />
    </Suspense>
  );
}
