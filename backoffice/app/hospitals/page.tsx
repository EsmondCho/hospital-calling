import { Suspense } from "react";

import { HospitalsList } from "./hospitals-list";

// HospitalsList reads filter/pagination state via useSearchParams, which
// requires a Suspense boundary to prerender (Next.js 16 build constraint).
export default function HospitalsPage() {
  return (
    <Suspense>
      <HospitalsList />
    </Suspense>
  );
}
