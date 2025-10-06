import React, { createContext, useContext, useState } from "react";

type SearchContextType = {
  query: string;
  page: number;
  setQuery: (q: string) => void;
  setPage: (p: number) => void;
};

const SearchContext = createContext<SearchContextType | undefined>(undefined);

export const SearchProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  return (
    <SearchContext.Provider value={{ query, page, setQuery, setPage }}>{children}</SearchContext.Provider>
  );
};

export function useSearch(): SearchContextType {
  const ctx = useContext(SearchContext);
  if (!ctx) {
    throw new Error("useSearch must be used within a SearchProvider");
  }
  return ctx;
}

export default SearchProvider;
