import { useEffect } from "react";

const SITE = "Echo Combat Stats";

/** Browser-tab title: "<page> · Echo Combat Stats" (tabs, history and bookmarks can be told apart). */
export function usePageTitle(page: string | null | undefined) {
  useEffect(() => {
    document.title = page ? `${page} · ${SITE}` : SITE;
    return () => {
      document.title = SITE;
    };
  }, [page]);
}
