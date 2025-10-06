import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

type SearchNavigationParams = {
  query?: string;
  author?: string;
  tags?: string[];
  includeDrafts?: boolean;
};

const normalizeTagList = (tags: string[] | undefined): string[] =>
  Array.from(new Set((tags ?? []).map((tag) => tag.trim().toLowerCase()).filter((tag) => tag.length > 0)));

export function useSearchNavigation() {
  const navigate = useNavigate();

  const goToSearch = useCallback(
    ({ query, author, tags, includeDrafts }: SearchNavigationParams) => {
      const params = new URLSearchParams();
      const normalizedQuery = query && query.trim().length > 0 ? query.trim() : "*";
      params.set("query", normalizedQuery);

      if (author && author.trim()) {
        params.set("author", author.trim().toLowerCase());
      }

      const normalizedTags = normalizeTagList(tags);
      if (normalizedTags.length > 0) {
        params.set("tags", normalizedTags.join(","));
      }

      if (includeDrafts) {
        params.set("includeDrafts", "true");
      }

      params.set("page", "1");
      navigate({ pathname: "/search", search: `?${params.toString()}` });
    },
    [navigate]
  );

  const goToTag = useCallback(
    (tag: string, options?: { includeDrafts?: boolean }) => {
      const normalized = tag.trim();
      if (!normalized) {
        return;
      }
      goToSearch({ query: "*", tags: [normalized], includeDrafts: options?.includeDrafts });
    },
    [goToSearch]
  );

  const goToAuthor = useCallback(
    (author: string, options?: { includeDrafts?: boolean }) => {
      const normalized = author.trim();
      if (!normalized) {
        return;
      }
      goToSearch({ query: "*", author: normalized, includeDrafts: options?.includeDrafts });
    },
    [goToSearch]
  );

  return { goToSearch, goToTag, goToAuthor };
}
