import {
  ChangeEvent,
  FocusEvent,
  KeyboardEvent,
  MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Badge,
  Box,
  Button,
  ButtonGroup,
  CloseButton,
  Flex,
  Grid,
  GridItem,
  Heading,
  HStack,
  IconButton,
  Image,
  Input,
  InputGroup,
  InputLeftElement,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Select,
  Slider,
  SliderFilledTrack,
  SliderThumb,
  SliderTrack,
  Spinner,
  Stack,
  Text,
  Tooltip,
  VStack,
} from "@chakra-ui/react";
import { AtSignIcon, ChevronDownIcon, SearchIcon } from "@chakra-ui/icons";
import { MdLocalOffer } from "react-icons/md";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { NotesStats, SearchResponse, SearchResult } from "../types";
import { useSearchNavigation } from "../hooks/useSearchNavigation";

type SearchPayload = {
  query: string;
  page: number;
  includeDrafts: boolean;
  allowDeleted: boolean;
  author?: string;
  tags?: string[];
};

export function SearchPage(): JSX.Element {
  const PAGE_SIZE = 20;

  const [searchParams, setSearchParams] = useSearchParams();
  const { goToTag, goToAuthor } = useSearchNavigation();

  const [query, setQuery] = useState("");
  const [authorFilter, setAuthorFilter] = useState("");
  const [authorSearch, setAuthorSearch] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tagSearch, setTagSearch] = useState("");
  const [tagFilters, setTagFilters] = useState<string[]>([]);
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [allowDeleted, setAllowDeleted] = useState(false);
  const [page, setPage] = useState(1);
  const [minScore, setMinScore] = useState(0);
  const [sortOption, setSortOption] = useState("relevance");
  const [isSliderTooltipOpen, setSliderTooltipOpen] = useState(false);

  const logoSrc = useMemo(() => new URL("assets/saraswati.png", import.meta.url).href, []);

  const statsQuery = useQuery<NotesStats>({
    queryKey: ["notes-stats"],
    queryFn: async () => {
      const { data } = await api.get<NotesStats>("/notes/stats");
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch all available authors for dropdown
  const authorsQuery = useQuery<string[]>({
    queryKey: ["all-authors"],
    queryFn: async () => {
      const { data } = await api.get<{ authors: string[] }>("/notes/authors");
      return data.authors || [];
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch all available tags for dropdown
  const tagsQuery = useQuery<string[]>({
    queryKey: ["all-tags"],
    queryFn: async () => {
      const { data } = await api.get<{ tags: string[] }>("/notes/tags");
      return data.tags || [];
    },
    staleTime: 5 * 60 * 1000,
  });

  const search = useMutation(
    async (payload: SearchPayload) => {
      const body: Record<string, unknown> = {
        query: payload.query,
        page: payload.page,
        page_size: PAGE_SIZE,
        sort_by: sortOption,
      };
      if (payload.author) {
        body.author = payload.author;
      }
      if (payload.tags && payload.tags.length > 0) {
        body.tags = payload.tags;
      }
      const { data } = await api.post<SearchResponse>(
        `/notes/search?includeDrafts=${payload.includeDrafts}&allowDeleted=${payload.allowDeleted}`,
        body
      );
      return data;
    }
  );

  const runSearch = search.mutate;

  const paramsSignature = searchParams.toString();

  useEffect(() => {
    const params = new URLSearchParams(paramsSignature);

    const rawQueryParam = params.get("query");
    const normalizedQueryParam = rawQueryParam === null ? "" : rawQueryParam === "*" ? "" : rawQueryParam;
    setQuery((prev) => (prev === normalizedQueryParam ? prev : normalizedQueryParam));

    const paramAuthor = params.get("author") ?? "";
    setAuthorFilter((prev) => (prev === paramAuthor ? prev : paramAuthor));

    const tagsParamRaw = params.get("tags") ?? "";
    const nextTags = tagsParamRaw
      ? Array.from(
        new Set(
          tagsParamRaw
            .split(",")
            .map((tag) => tag.trim().toLowerCase())
            .filter((tag) => tag.length > 0)
        )
      )
      : [];
    setTagFilters((prev) => {
      const prevKey = prev.join(",");
      const nextKey = nextTags.join(",");
      if (prevKey === nextKey) {
        return prev;
      }
      return nextTags;
    });
    setTagInput("");

    const includeDraftsParam = params.get("includeDrafts") === "true";
    setIncludeDrafts((prev) => (prev === includeDraftsParam ? prev : includeDraftsParam));

    const allowDeletedParam = params.get("allowDeleted") === "true";
    setAllowDeleted((prev) => (prev === allowDeletedParam ? prev : allowDeletedParam));

    const pageParam = Math.max(parseInt(params.get("page") ?? "1", 10) || 1, 1);
    setPage((prev) => (prev === pageParam ? prev : pageParam));

  const sortParam = params.get("sort") ?? "relevance";
  setSortOption((prev) => (prev === sortParam ? prev : sortParam));

    const hasExplicitQuery = rawQueryParam !== null;
    const hasAuthorFilter = paramAuthor.trim().length > 0;
    const hasTagFilters = nextTags.length > 0;
    const hasIncludeDraftsParam = params.has("includeDrafts");
    const hasAllowDeletedParam = params.has("allowDeleted");
    const hasPageParam = params.has("page");

    if (!(hasExplicitQuery || hasAuthorFilter || hasTagFilters || hasIncludeDraftsParam || hasAllowDeletedParam || hasPageParam)) {
      return;
    }

    const requestQuery = normalizedQueryParam.length > 0 ? normalizedQueryParam : "*";
    const requestAuthor = paramAuthor.trim().length > 0 ? paramAuthor.trim().toLowerCase() : undefined;

    runSearch({
      query: requestQuery,
      page: pageParam,
      includeDrafts: includeDraftsParam,
      allowDeleted: allowDeletedParam,
      author: requestAuthor,
      tags: nextTags,
    });

    if (pageParam === 1) {
      setMinScore(0);
      setSortOption("relevance");
    }
  }, [paramsSignature, runSearch]);

  const computeQueryParam = useCallback((): string => {
    const param = searchParams.get("query");
    if (param && param.trim().length > 0) {
      return param.trim();
    }
    const trimmed = query.trim();
    return trimmed.length > 0 ? trimmed : "*";
  }, [query, searchParams]);

  const buildAndSetSearchParams = useCallback(
    (
      nextPage: number,
      draftsFlag: boolean,
      deletedFlag: boolean,
      overrides?: Partial<{ query: string; author: string; tags: string[] }>
    ) => {
      const resolvedQuery = overrides?.query ?? query;
      const normalizedQuery = resolvedQuery.trim();
      const queryToken =
        resolvedQuery === "*"
          ? "*"
          : normalizedQuery.length > 0
            ? normalizedQuery
            : "";

      const resolvedAuthor = overrides?.author ?? authorFilter;
      const normalizedAuthor = resolvedAuthor.trim().length > 0 ? resolvedAuthor.trim().toLowerCase() : "";

      const resolvedTags = overrides?.tags ?? tagFilters;
      const normalizedTags = Array.from(
        new Set(resolvedTags.map((tag) => tag.trim().toLowerCase()).filter((tag) => tag.length > 0))
      );

        const params = new URLSearchParams();
        if (queryToken) {
          params.set("query", queryToken);
        }
        if (normalizedAuthor) {
          params.set("author", normalizedAuthor);
        }
        if (normalizedTags.length > 0) {
          params.set("tags", normalizedTags.join(","));
        }
        if (draftsFlag) {
          params.set("includeDrafts", "true");
        }
        if (deletedFlag) {
          params.set("allowDeleted", "true");
        }
        if (nextPage > 1) {
          params.set("page", nextPage.toString());
        }

      setSearchParams(params);
    },
    [authorFilter, query, tagFilters, setSearchParams]
  );

  const handleAddTag = useCallback((value?: string) => {
    const rawValue = (value ?? "").trim().toLowerCase();
    if (!rawValue) {
      setTagInput("");
      return;
    }
    setTagFilters((prev) => (prev.includes(rawValue) ? prev : [...prev, rawValue]));
    setTagInput("");
  }, []);

  const handleTagInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAddTag(event.currentTarget.value);
    }
  };

  const handleRemoveTag = useCallback(
    (tag: string) => {
      setTagFilters((prev) => {
        if (!prev.includes(tag)) {
          return prev;
        }
        const next = prev.filter((item) => item !== tag);
        const active = searchParams.toString().length > 0;
        if (active) {
          const nextQuery = computeQueryParam();
          buildAndSetSearchParams(1, includeDrafts, allowDeleted, { tags: next, query: nextQuery });
        }
        return next;
      });
    },
    [buildAndSetSearchParams, computeQueryParam, includeDrafts, allowDeleted, searchParams]
  );

  const handleClearFilters = useCallback(() => {
    const active = searchParams.toString().length > 0;
    setAuthorFilter("");
    setTagFilters([]);
    setTagInput("");
    if (active) {
      setMinScore(0);
      setSortOption("relevance");
      setPage(1);
      const nextQuery = computeQueryParam();
      buildAndSetSearchParams(1, includeDrafts, allowDeleted, { author: "", tags: [], query: nextQuery });
    }
  }, [buildAndSetSearchParams, computeQueryParam, includeDrafts, searchParams]);

  const handleSearch = useCallback(() => {
    const pendingTag = tagInput.trim().toLowerCase();
    const nextTags = pendingTag && !tagFilters.includes(pendingTag) ? [...tagFilters, pendingTag] : tagFilters;
    if (pendingTag && !tagFilters.includes(pendingTag)) {
      setTagFilters(nextTags);
    }

    setTagInput("");
    setMinScore(0);
    setSortOption("relevance");
    setPage(1);

    const nextQuery = query.trim().length > 0 ? query.trim() : "*";
    buildAndSetSearchParams(1, includeDrafts, allowDeleted, { query: nextQuery, tags: nextTags });
  }, [buildAndSetSearchParams, includeDrafts, query, tagFilters, tagInput]);

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleSearch();
    }
  };

  const handleIncludeDraftsChange = useCallback(
    (nextValue: boolean) => {
      setIncludeDrafts(nextValue);
      setMinScore(0);
      setSortOption("relevance");
      setPage(1);
      const nextQuery = computeQueryParam();
      buildAndSetSearchParams(1, nextValue, allowDeleted, { query: nextQuery });
    },
    [buildAndSetSearchParams, computeQueryParam, allowDeleted]
  );

  const handleAllowDeletedChange = useCallback(
    (nextValue: boolean) => {
      setAllowDeleted(nextValue);
      setMinScore(0);
      setSortOption("relevance");
      setPage(1);
      const nextQuery = computeQueryParam();
      buildAndSetSearchParams(1, includeDrafts, nextValue, { query: nextQuery });
    },
    [buildAndSetSearchParams, computeQueryParam, includeDrafts]
  );

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (nextPage < 1) {
        return;
      }
      setPage(nextPage);
      const nextQuery = computeQueryParam();
      buildAndSetSearchParams(nextPage, includeDrafts, allowDeleted, { query: nextQuery });
    },
    [buildAndSetSearchParams, computeQueryParam, includeDrafts]
  );

  const hasSearched = search.isLoading || search.isSuccess;

  const currentResults = search.data?.items ?? [];
  const filteredResults = currentResults.filter((result: SearchResult) => result.score * 100 >= minScore);
  const sortedResults = sortOption === "relevance"
    ? filteredResults
    : [...filteredResults].sort((a, b) => {
      const aDate = new Date(a.version.created_at).getTime();
      const bDate = new Date(b.version.created_at).getTime();
      const aUser = a.version.created_by.toLowerCase();
      const bUser = b.version.created_by.toLowerCase();

      switch (sortOption) {
        case "date-desc":
          return bDate - aDate;
        case "date-asc":
          return aDate - bDate;
        case "user-asc":
          return aUser.localeCompare(bUser);
        case "user-desc":
          return bUser.localeCompare(aUser);
        default:
          return 0;
      }
    });
  const totalMatches = search.data?.total ?? 0;
  const totalPages = search.data?.total_pages ?? 0;
  const hasActiveParams = searchParams.toString().length > 0;

  return (
    <Box maxW="1400px" mx="auto" w="100%" px={{ base: 4, md: 6 }}>
      {/* Hero/Search Section */}
      <Box
        py={hasSearched ? 6 : 12}
        transition="all 0.3s ease"
      >
        <Stack spacing={8} align="center">
          {!hasSearched && (
            <Stack spacing={4} textAlign="center" maxW="600px">
              <Image src={logoSrc} alt="Saraswati" mx="auto" maxW="200px" mb={2} opacity={0.85} />
              <Heading size="xl" fontWeight={600} color="gray.800" letterSpacing="tight">
                Search with Saraswati
              </Heading>
              <Text fontSize="md" color="gray.600" fontWeight={400}>
                Explore {statsQuery.data?.total_notes ?? "thousands of"} notes with semantic search
              </Text>
            </Stack>
          )}

          {/* Main Search Input */}
          <Stack spacing={3} w="100%" maxW={hasSearched ? '100%' : '900px'}>
            <InputGroup size="md">
              <InputLeftElement pointerEvents="none" h="full">
                <SearchIcon color="gray.400" boxSize={4} />
              </InputLeftElement>
              <Input
                value={query}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Search by keyword, tag, or semantic meaning..."
                bg="white"
                border="1px solid"
                borderColor="gray.200"
                borderRadius="lg"
                h="44px"
                pl="40px"
                fontSize="md"
                _hover={{ borderColor: "gray.300" }}
                _focus={{
                  borderColor: "blue.400",
                  boxShadow: "0 0 0 3px rgba(59, 130, 246, 0.1)",
                  outline: "none"
                }}
                _placeholder={{ color: "gray.400" }}
              />
              <Button
                onClick={handleSearch}
                size="m"
                colorScheme="blue"
                isLoading={search.isLoading}
                px={6}
                fontWeight={500}
              >
                Search
              </Button>
            </InputGroup>

            {/* All Controls in One Row */}
            <HStack spacing={2} w="100%" flexWrap="wrap">
              {/* Include Drafts Toggle */}
              <HStack spacing={2}>
                <Text fontSize="xs" color="gray.600" fontWeight={500}>Drafts:</Text>
                <ButtonGroup size="xs" isAttached variant="outline">
                  <Button
                    onClick={() => handleIncludeDraftsChange(false)}
                    bg={!includeDrafts ? "github.accent.subtle" : "transparent"}
                    color={!includeDrafts ? "github.accent.fg" : "github.fg.default"}
                    borderColor="github.border.default"
                    _hover={{ bg: !includeDrafts ? "github.accent.subtle" : "github.bg.secondary" }}
                    fontSize="xs"
                    px={3}
                  >
                    No
                  </Button>
                  <Button
                    onClick={() => handleIncludeDraftsChange(true)}
                    bg={includeDrafts ? "github.accent.subtle" : "transparent"}
                    color={includeDrafts ? "github.accent.fg" : "github.fg.default"}
                    borderColor="github.border.default"
                    _hover={{ bg: includeDrafts ? "github.accent.subtle" : "github.bg.secondary" }}
                    fontSize="xs"
                    px={3}
                  >
                    Yes
                  </Button>
                </ButtonGroup>
              </HStack>

              {/* Show Deleted Toggle */}
              <HStack spacing={2}>
                <Text fontSize="xs" color="gray.600" fontWeight={500}>Deleted:</Text>
                <ButtonGroup size="xs" isAttached variant="outline">
                  <Button
                    onClick={() => handleAllowDeletedChange(false)}
                    bg={!allowDeleted ? "github.accent.subtle" : "transparent"}
                    color={!allowDeleted ? "github.accent.fg" : "github.fg.default"}
                    borderColor="github.border.default"
                    _hover={{ bg: !allowDeleted ? "github.accent.subtle" : "github.bg.secondary" }}
                    fontSize="xs"
                    px={3}
                  >
                    No
                  </Button>
                  <Button
                    onClick={() => handleAllowDeletedChange(true)}
                    bg={allowDeleted ? "github.accent.subtle" : "transparent"}
                    color={allowDeleted ? "github.accent.fg" : "github.fg.default"}
                    borderColor="github.border.default"
                    _hover={{ bg: allowDeleted ? "github.accent.subtle" : "github.bg.secondary" }}
                    fontSize="xs"
                    px={3}
                  >
                    Yes
                  </Button>
                </ButtonGroup>
              </HStack>

              {/* Sort options */}
              <HStack spacing={2}>
                <Text fontSize="xs" color="gray.600" fontWeight={500}>Sort:</Text>
                <Select
                  size="sm"
                  value={sortOption}
                  onChange={(e) => {
                    const next = e.target.value;
                    setSortOption(next);
                    // rebuild params and trigger a search
                    buildAndSetSearchParams(1, includeDrafts, allowDeleted, { query: computeQueryParam(), author: authorFilter, tags: tagFilters });
                  }}
                >
                  <option value="relevance">Relevance</option>
                  <option value="upvotes">Upvotes</option>
                  <option value="downvotes">Downvotes</option>
                </Select>
              </HStack>

              {/* Author Dropdown */}
              <Menu closeOnSelect={false}>
                {() => (
                  <>
                    <MenuButton
                      as={Button}
                      rightIcon={<ChevronDownIcon />}
                      size="xs"
                      variant="outline"
                      borderColor="gray.200"
                      _hover={{ bg: "gray.50", borderColor: "gray.300" }}
                      _active={{ bg: "gray.100" }}
                      fontWeight={authorFilter ? 500 : 400}
                      color={authorFilter ? "blue.600" : "gray.600"}
                    >
                      <HStack spacing={1}>
                        <AtSignIcon fontSize="xs" />
                        <Text>{authorFilter || "Author"}</Text>
                      </HStack>
                    </MenuButton>
                    <MenuList maxH="300px" overflowY="auto" shadow="lg">
                      <Box px={3} py={2}>
                        <Input
                          placeholder="Search authors..."
                          size="xs"
                          value={authorSearch}
                          onChange={(e: ChangeEvent<HTMLInputElement>) => setAuthorSearch(e.target.value)}
                          autoFocus
                        />
                      </Box>
                      <Box h="1px" bg="gray.100" />
                      {authorFilter && (
                        <>
                          <MenuItem
                            onClick={() => {
                              setAuthorFilter("");
                              if (hasSearched) {
                                buildAndSetSearchParams(1, includeDrafts, allowDeleted, { author: "" });
                              }
                            }}
                            fontWeight={500}
                            color="red.600"
                          >
                            Clear author filter
                          </MenuItem>
                          <Box h="1px" bg="gray.100" my={1} />
                        </>
                      )}
                      {authorsQuery.data?.filter((author: string) =>
                        author.toLowerCase().includes(authorSearch.toLowerCase())
                      ).map((author: string) => (
                        <MenuItem
                          key={author}
                          onClick={() => {
                            setAuthorFilter(author);
                            if (hasSearched) {
                              buildAndSetSearchParams(1, includeDrafts, allowDeleted, { author });
                            }
                          }}
                          bg={authorFilter === author ? "blue.50" : undefined}
                          fontWeight={authorFilter === author ? 500 : 400}
                        >
                          <HStack>
                            <AtSignIcon fontSize="xs" color="gray.500" />
                            <Text>{author}</Text>
                          </HStack>
                        </MenuItem>
                      ))}
                    </MenuList>
                  </>
                )}
              </Menu>

              {/* Tags Dropdown */}
              <Menu closeOnSelect={false}>
                {() => (
                  <>
                    <MenuButton
                      as={Button}
                      rightIcon={<ChevronDownIcon />}
                      size="xs"
                      variant="outline"
                      borderColor="gray.200"
                      _hover={{ bg: "gray.50", borderColor: "gray.300" }}
                      _active={{ bg: "gray.100" }}
                      fontWeight={tagFilters.length > 0 ? 500 : 400}
                      color={tagFilters.length > 0 ? "blue.600" : "gray.600"}
                    >
                      <HStack spacing={1}>
                        <MdLocalOffer size={12} />
                        <Text>
                          {tagFilters.length > 0 ? `${tagFilters.length} tag${tagFilters.length > 1 ? "s" : ""}` : "Tags"}
                        </Text>
                      </HStack>
                    </MenuButton>
                    <MenuList maxH="300px" overflowY="auto" shadow="lg">
                      <Box px={3} py={2}>
                        <Input
                          placeholder="Search tags..."
                          size="xs"
                          value={tagSearch}
                          onChange={(e: ChangeEvent<HTMLInputElement>) => setTagSearch(e.target.value)}
                          autoFocus
                        />
                      </Box>
                      <Box h="1px" bg="gray.100" />
                      {tagFilters.length > 0 && (
                        <>
                          <MenuItem
                            onClick={() => {
                              setTagFilters([]);
                              if (hasSearched) {
                                buildAndSetSearchParams(1, includeDrafts, allowDeleted, { tags: [] });
                              }
                            }}
                            fontWeight={500}
                            color="red.600"
                          >
                            Clear all tags
                          </MenuItem>
                          <Box h="1px" bg="gray.100" my={1} />
                        </>
                      )}
                      {tagsQuery.data?.filter((tag: string) =>
                        tag.toLowerCase().includes(tagSearch.toLowerCase())
                      ).map((tag: string) => {
                        const isSelected = tagFilters.includes(tag);
                        return (
                          <MenuItem
                            key={tag}
                            onClick={() => {
                              const nextTags = isSelected
                                ? tagFilters.filter((t) => t !== tag)
                                : [...tagFilters, tag];
                              setTagFilters(nextTags);
                              if (hasSearched) {
                                buildAndSetSearchParams(1, includeDrafts, allowDeleted, { tags: nextTags });
                              }
                            }}
                            bg={isSelected ? "blue.50" : undefined}
                            fontWeight={isSelected ? 500 : 400}
                          >
                            <HStack justify="space-between" w="100%">
                              <HStack>
                                <MdLocalOffer size={12} color={isSelected ? "#3182ce" : "#718096"} />
                                <Text>{tag}</Text>
                              </HStack>
                              {isSelected && (
                                <Badge colorScheme="blue" fontSize="2xs">
                                  ✓
                                </Badge>
                              )}
                            </HStack>
                          </MenuItem>
                        );
                      })}
                    </MenuList>
                  </>
                )}
              </Menu>

              {(authorFilter || tagFilters.length > 0) && (
                <IconButton
                  aria-label="Clear filters"
                  icon={<CloseButton size="sm" />}
                  size="xs"
                  variant="ghost"
                  onClick={handleClearFilters}
                  color="gray.600"
                  _hover={{ bg: "gray.100" }}
                />
              )}

              {/* Min Score Slider */}
              {search.data && (
                <HStack spacing={2} minW="180px" maxW="250px">
                  <Text fontSize="xs" color="gray.600" fontWeight={500} whiteSpace="nowrap">Min:</Text>
                  <Slider
                    min={0}
                    max={100}
                    step={5}
                    value={minScore}
                    onChange={(value: number) => setMinScore(value)}
                    onMouseEnter={() => setSliderTooltipOpen(true)}
                    onMouseLeave={() => setSliderTooltipOpen(false)}
                    flex={1}
                    size="xs"
                  >
                    <SliderTrack bg="gray.200" h="4px">
                      <SliderFilledTrack bg="blue.500" />
                    </SliderTrack>
                    <Tooltip
                      hasArrow
                      placement="top"
                      isOpen={isSliderTooltipOpen}
                      label={`${minScore}%`}
                      bg="blue.500"
                      color="white"
                    >
                      <SliderThumb boxSize={4} />
                    </Tooltip>
                  </Slider>
                  <Badge
                    colorScheme="blue"
                    fontSize="2xs"
                    px={2}
                    py={0.5}
                    minW="35px"
                    textAlign="center"
                  >
                    {minScore}%
                  </Badge>
                </HStack>
              )}

              {/* Sort Dropdown */}
              <HStack spacing={2} 
                ml="auto">
                <Text fontSize="xs" color="gray.600" fontWeight={500}>Sort:</Text>
                <Select
                  size="xs"
                  value={sortOption}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => setSortOption(event.target.value)}
                  borderColor="github.border.default"
                  maxW="170px"
                  fontSize="xs"
                  _hover={{ borderColor: "github.border.emphasis" }}
                >
                  <option value="relevance">Relevance</option>
                  <option value="date-desc">Newest first</option>
                  <option value="date-asc">Oldest first</option>
                  <option value="user-asc">Author A → Z</option>
                  <option value="user-desc">Author Z → A</option>
                </Select>
              </HStack>

            </HStack>

            {/* Active Filters Display */}
            {(authorFilter || tagFilters.length > 0) && (
              <HStack spacing={2} flexWrap="wrap">
                {authorFilter && (
                  <Badge
                    display="inline-flex"
                    alignItems="center"
                    gap={1.5}
                    fontSize="xs"
                    px={3}
                    py={1}
                    borderRadius="full"
                    bg="purple.50"
                    color="purple.700"
                    border="1px solid"
                    borderColor="purple.200"
                    textTransform="lowercase"
                    cursor="pointer"
                    title="Double-click to search by this author"
                    onDoubleClick={() => goToAuthor(authorFilter)}
                  >
                    <AtSignIcon boxSize={2.5} />
                    {authorFilter}
                    <CloseButton
                      size="sm"
                      onClick={(event: ReactMouseEvent<HTMLButtonElement>) => {
                        event.stopPropagation();
                        setAuthorFilter("");
                        if (hasSearched) {
                          buildAndSetSearchParams(1, includeDrafts, allowDeleted, { author: "" });
                        }
                      }}
                      ml={1}
                    />
                  </Badge>
                )}
                {tagFilters.map((tag: string) => (
                  <Badge
                    key={tag}
                    display="inline-flex"
                    alignItems="center"
                    gap={1.5}
                    fontSize="xs"
                    px={3}
                    py={1}
                    borderRadius="full"
                    bg="blue.50"
                    color="blue.700"
                    border="1px solid"
                    borderColor="blue.200"
                    textTransform="lowercase"
                    cursor="pointer"
                    title="Double-click to search by this tag"
                    onDoubleClick={() => goToTag(tag)}
                    fontWeight={500}
                  >
                    <MdLocalOffer size={14} />
                    {tag}
                    <CloseButton
                      size="sm"
                      onClick={(event: ReactMouseEvent<HTMLButtonElement>) => {
                        event.stopPropagation();
                        handleRemoveTag(tag);
                      }}
                      onDoubleClick={(event: ReactMouseEvent<HTMLButtonElement>) => event.stopPropagation()}
                      aria-label={`Remove tag ${tag}`}
                      ml={0.5}
                      color="white"
                      _hover={{ bg: "blue.700" }}
                    />
                  </Badge>
                ))}
              </HStack>
            )}
          </Stack>

          {/* Stats - show only when not searched */}
          {!hasSearched && statsQuery.data && (
            <Grid
              templateColumns={{ base: "repeat(2, 1fr)", md: "repeat(3, 1fr)", lg: "repeat(6, 1fr)" }}
              gap={4}
              w="100%"
              maxW="900px"
              mt={2}
            >
              <Box bg="white" p={5} borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center" boxShadow="sm">
                <Text fontSize="3xl" fontWeight="700" color="gray.800">
                  {statsQuery.data.total_notes}
                </Text>
                <Text fontSize="xs" color="gray.500" fontWeight={500} textTransform="uppercase" letterSpacing="wide">Notes</Text>
              </Box>
              <Box bg="white" p={5} borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center" boxShadow="sm">
                <Text fontSize="3xl" fontWeight="700" color="green.500">
                  {statsQuery.data.approved_versions}
                </Text>
                <Text fontSize="xs" color="gray.500" fontWeight={500} textTransform="uppercase" letterSpacing="wide">Approved</Text>
              </Box>
              <Box bg="white" p={5} borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center" boxShadow="sm">
                <Text fontSize="3xl" fontWeight="700" color="orange.500">
                  {statsQuery.data.needs_review_versions}
                </Text>
                <Text fontSize="xs" color="gray.500" fontWeight={500} textTransform="uppercase" letterSpacing="wide">Review</Text>
              </Box>
              <Box bg="white" p={5} borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center" boxShadow="sm">
                <Text fontSize="3xl" fontWeight="700" color="blue.500">
                  {statsQuery.data.draft_versions}
                </Text>
                <Text fontSize="xs" color="gray.500" fontWeight={500} textTransform="uppercase" letterSpacing="wide">Drafts</Text>
              </Box>
              <Box bg="white" p={5} borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center" boxShadow="sm">
                <Text fontSize="3xl" fontWeight="700" color="purple.500">
                  {statsQuery.data.distinct_tags}
                </Text>
                <Text fontSize="xs" color="gray.500" fontWeight={500} textTransform="uppercase" letterSpacing="wide">Tags</Text>
              </Box>
              <Box bg="white" p={5} borderRadius="xl" border="1px solid" borderColor="gray.100" textAlign="center" boxShadow="sm">
                <Text fontSize="3xl" fontWeight="700" color="teal.500">
                  {statsQuery.data.active_authors}
                </Text>
                <Text fontSize="xs" color="gray.500" fontWeight={500} textTransform="uppercase" letterSpacing="wide">Authors</Text>
              </Box>
            </Grid>
          )}
        </Stack>
      </Box>

      {/* Results Section */}
      {hasSearched && (
        <Box mt={6}>
          {search.isLoading && (
            <Flex justify="center" py={12}>
              <Stack spacing={3} align="center">
                <Spinner thickness="3px" speed="0.65s" color="blue.500" size="xl" />
                <Text fontSize="sm" color="github.fg.muted">Searching knowledge base...</Text>
              </Stack>
            </Flex>
          )}

          {search.isError && (
            <Box textAlign="center" py={8}>
              <Text fontSize="lg" fontWeight="500" color="red.500" mb={2}>
                Search Error
              </Text>
              <Text fontSize="sm" color="github.fg.muted">
                Something went wrong while searching. Please try again.
              </Text>
            </Box>
          )}

          {search.data && currentResults.length === 0 && (
            <Box textAlign="center" py={8}>
              <Text fontSize="lg" fontWeight="500" color="github.fg.muted" mb={2}>
                No Results Found
              </Text>
              <Text fontSize="sm" color="github.fg.muted">
                Try adjusting your search terms or filters.
              </Text>
            </Box>
          )}

          {/* Results Count & Content */}
          {search.data && currentResults.length > 0 && (
            <>
              <Flex justify="space-between" align="center" mb={4}>
                <Text fontSize="xs" color="github.fg.muted" fontWeight={500}>
                  Showing <Text as="span" fontWeight={600}>{sortedResults.length}</Text> of <Text as="span" fontWeight={600}>{currentResults.length}</Text> results · Total: <Text as="span" fontWeight={600}>{totalMatches}</Text>
                </Text>
              </Flex>

              {sortedResults.length === 0 && (
                <Box textAlign="center" py={12} px={6}>
                  <Text fontSize="lg" color="gray.600" fontWeight={500}>
                    No results meet the selected score threshold.
                  </Text>
                  <Text fontSize="sm" color="gray.500" mt={2}>
                    Lower the minimum match score to see more results.
                  </Text>
                </Box>
              )}

              <Stack spacing={3}>
                {sortedResults.map((result: SearchResult) => (
                  <Box
                    key={result.version.version_id}
                    bg="github.bg.primary"
                    border="1px solid"
                    borderColor="github.border.default"
                    borderRadius="md"
                    overflow="hidden"
                    transition="all 0.2s ease"
                    _hover={{ borderColor: "github.border.emphasis", transform: "translateY(-1px)" }}
                  >
                    <Box borderBottom="1px solid" borderColor="github.border.default" py={3} px={4}>
                      <Flex justify="space-between" align={{ base: "flex-start", md: "center" }} gap={3} direction={{ base: "column", md: "row" }}>
                        <Stack spacing={1} flex={1} minW={0}>
                          <Heading size="sm" fontWeight={600} color="github.accent.fg" noOfLines={1}>
                            <Link to={`/note/${result.version.id}`}>{result.version.title}</Link>
                          </Heading>
                          <Text fontSize="xs" color="github.fg.muted">
                            {new Date(result.version.created_at).toLocaleDateString()} · Note {result.version.id}
                          </Text>
                        </Stack>
                        <HStack spacing={2} flexShrink={0}>
                          <Badge
                            fontSize="2xs"
                            px={2}
                            py={0.5}
                            borderRadius="full"
                            bg={result.version.state === "approved" ? "green.100" : result.version.state === "needs_review" ? "orange.100" : "blue.100"}
                            color={result.version.state === "approved" ? "green.800" : result.version.state === "needs_review" ? "orange.800" : "blue.800"}
                            textTransform="uppercase"
                            letterSpacing="wide"
                          >
                            {result.version.state === "approved" ? "Approved" : result.version.state === "needs_review" ? "Review" : "Draft"}
                          </Badge>
                          <Badge
                            fontSize="2xs"
                            px={2}
                            py={0.5}
                            borderRadius="full"
                            bg="green.100"
                            color="green.800"
                            textTransform="uppercase"
                            letterSpacing="wide"
                          >
                            {(result.score * 100).toFixed(0)}% match
                          </Badge>
                          {result.version.state === "needs_review" && result.version.active_review_id && (
                            <Button
                              as={Link}
                              to={`/review/${result.version.active_review_id}`}
                              size="sm"
                              variant="secondary"
                            >
                              Review
                            </Button>
                          )}
                        </HStack>
                      </Flex>
                    </Box>
                    <Box py={3} px={4}>
                      <Stack spacing={3} fontSize="sm">
                        <Text color="github.fg.default" noOfLines={2}>
                          {result.version.content}
                        </Text>
                        <Flex justify="space-between" align="center" flexWrap="wrap" gap={3}>
                          <HStack spacing={2} flexWrap="wrap">
                            <Badge
                              display="inline-flex"
                              alignItems="center"
                              gap={1}
                              fontSize="2xs"
                              px={2}
                              py={0.5}
                              borderRadius="full"
                              bg="gray.200"
                              color="gray.700"
                              textTransform="lowercase"
                              cursor="pointer"
                              title="Double-click to search by this author"
                              onDoubleClick={() => goToAuthor(result.version.created_by)}
                            >
                              @{result.version.created_by.toLowerCase()}
                            </Badge>
                            {result.version.tags.slice(0, 5).map((tag: string) => (
                              <Badge
                                key={tag}
                                display="inline-flex"
                                alignItems="center"
                                gap={1}
                                fontSize="2xs"
                                px={2}
                                py={0.5}
                                borderRadius="full"
                                bg="blue.50"
                                color="blue.700"
                                textTransform="lowercase"
                                cursor="pointer"
                                title="Double-click to search by this tag"
                                onDoubleClick={() => goToTag(tag)}
                              >
                                #{tag.toLowerCase()}
                              </Badge>
                            ))}
                          </HStack>
                          <HStack spacing={3} fontSize="xs" color="github.fg.muted">
                            <HStack spacing={1}>
                              <Text>↑</Text>
                              <Text fontWeight={500}>{result.version.upvotes}</Text>
                            </HStack>
                            <HStack spacing={1}>
                              <Text>↓</Text>
                              <Text fontWeight={500}>{result.version.downvotes}</Text>
                            </HStack>
                          </HStack>
                        </Flex>
                      </Stack>
                    </Box>
                  </Box>
                ))}
              </Stack>

              {/* Pagination */}
              {totalPages > 1 && (
                <Flex
                  justify="space-between"
                  align="center"
                  mt={4}
                >
                  <Text fontSize="xs" color="github.fg.muted" fontWeight={500}>
                    Page <strong>{page}</strong> of <strong>{totalPages}</strong>
                  </Text>
                  <ButtonGroup size="sm" spacing={2}>
                    <Button
                      onClick={() => handlePageChange(Math.max(1, page - 1))}
                      isDisabled={page <= 1 || search.isLoading}
                      variant="outline"
                      borderColor="github.border.default"
                    >
                      ← Previous
                    </Button>
                    <Button
                      onClick={() => handlePageChange(page + 1)}
                      isDisabled={page >= totalPages || search.isLoading}
                      variant="secondary"
                    >
                      Next →
                    </Button>
                  </ButtonGroup>
                </Flex>
              )}
            </>
          )}
        </Box>
      )}
    </Box>
  );
}
