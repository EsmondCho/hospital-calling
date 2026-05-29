"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

// URL-state page-number pagination for offset-paginated lists.
//
// Keeps the 1-based `page` in the URL so paging survives navigating into a
// detail page and back. Other search params (filters) are left untouched.
// `replace` (not push) so back/forward history isn't polluted with each page.
export function usePagePagination() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const page = Math.max(1, Number(searchParams.get("page")) || 1);

  const setPage = (next: number) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next > 1) params.set("page", String(next));
    else params.delete("page");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  return { page, setPage };
}
