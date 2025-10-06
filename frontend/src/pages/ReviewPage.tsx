import { ChangeEvent, useMemo, useState } from "react";
import {
  Avatar,
  Badge,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardBody,
  CardHeader,
  Flex,
  Heading,
  HStack,
  Icon,
  Select,
  Spinner,
  Stack,
  Text,
  Tooltip
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";
import dayjs from "dayjs";
import { MdOutlineRateReview } from "react-icons/md";

import { api } from "../api/client";
import { ReviewStatus, ReviewSummary } from "../types";
import { useSearchNavigation } from "../hooks/useSearchNavigation";

type ScopeOption = "inbox" | "all";
type StatusPreset = "active" | "open" | "changes_requested" | "merged" | "closed" | "all";

const STATUS_PRESETS: Record<StatusPreset, ReviewStatus[]> = {
  active: ["open", "changes_requested"],
  open: ["open"],
  changes_requested: ["changes_requested"],
  merged: ["merged"],
  closed: ["closed"],
  all: []
};

const STATUS_BADGES: Record<ReviewStatus, { bg: string; color: string; label: string }> = {
  open: { bg: "github.accent.subtle", color: "github.accent.fg", label: "Open" },
  changes_requested: { bg: "orange.100", color: "orange.800", label: "Changes requested" },
  merged: { bg: "green.100", color: "green.800", label: "Committed" },
  closed: { bg: "gray.200", color: "gray.700", label: "Closed" }
};

export function ReviewPage(): JSX.Element {
  const navigate = useNavigate();
  const { goToTag, goToAuthor } = useSearchNavigation();

  const [scope, setScope] = useState<ScopeOption>("inbox");
  const [statusPreset, setStatusPreset] = useState<StatusPreset>("active");

  const statuses = STATUS_PRESETS[statusPreset];

  const reviewsQuery = useQuery<ReviewSummary[]>(
    ["reviews", { scope, statuses }],
    async () => {
      const params: Record<string, string> = {};
      if (scope === "inbox") {
        params.mine = "true";
      }
      if (statuses.length > 0) {
        params.status = statuses.join(",");
      }
      const { data } = await api.get<ReviewSummary[]>("/reviews", { params });
      return data;
    }
  );

  const reviews = useMemo(() => {
    if (!reviewsQuery.data) {
      return [];
    }
    const sorted = [...reviewsQuery.data];
    sorted.sort((a, b) => new Date(b.review.updated_at).getTime() - new Date(a.review.updated_at).getTime());
    return sorted;
  }, [reviewsQuery.data]);

  const emptyMessage = scope === "inbox"
    ? "You're all caught up. Reviews assigned to you will appear here."
    : "No reviews match this filter right now.";

  return (
    <Stack spacing={6}>
      <Flex direction={{ base: "column", md: "row" }} justify="space-between" gap={4}>
        <Stack spacing={1}>
          <Heading size="lg" fontWeight={600} display="flex" alignItems="center" gap={2}>
            <Icon as={MdOutlineRateReview} color="github.accent.fg" boxSize={6} />
            Reviews
          </Heading>
          <Text fontSize="sm" color="github.fg.muted">
            Track submissions, leave feedback, and merge knowledge updates.
          </Text>
        </Stack>
        <Stack direction={{ base: "column", md: "row" }} spacing={3} align={{ base: "stretch", md: "center" }}>
          <ButtonGroup size="sm" variant="outline" isAttached>
            <Button
              onClick={() => setScope("inbox")}
              bg={scope === "inbox" ? "github.accent.subtle" : "transparent"}
              color={scope === "inbox" ? "github.accent.fg" : "github.fg.default"}
              borderColor="github.border.default"
              _hover={{ bg: scope === "inbox" ? "github.accent.subtle" : "github.bg.secondary" }}
            >
              My queue
            </Button>
            <Button
              onClick={() => setScope("all")}
              bg={scope === "all" ? "github.accent.subtle" : "transparent"}
              color={scope === "all" ? "github.accent.fg" : "github.fg.default"}
              borderColor="github.border.default"
              _hover={{ bg: scope === "all" ? "github.accent.subtle" : "github.bg.secondary" }}
            >
              All reviews
            </Button>
          </ButtonGroup>
          <Select
            size="sm"
            value={statusPreset}
            onChange={(event: ChangeEvent<HTMLSelectElement>) => setStatusPreset(event.target.value as StatusPreset)}
            bg="github.bg.primary"
            borderColor="github.border.default"
            maxW="220px"
          >
            <option value="active">Active (open & changes requested)</option>
            <option value="open">Open only</option>
            <option value="changes_requested">Needs author updates</option>
            <option value="merged">Committed</option>
            <option value="closed">Closed</option>
            <option value="all">All statuses</option>
          </Select>
        </Stack>
      </Flex>

      {reviewsQuery.isLoading && (
        <Flex justify="center" py={16}>
          <Spinner size="xl" color="github.accent.emphasis" thickness="3px" />
        </Flex>
      )}

      {!reviewsQuery.isLoading && reviews.length === 0 && (
        <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <CardBody>
            <Heading size="sm" fontWeight={600} mb={1}>
              {scope === "inbox" ? "Nothing awaiting you" : "No reviews found"}
            </Heading>
            <Text fontSize="sm" color="github.fg.muted">
              {emptyMessage}
            </Text>
          </CardBody>
        </Card>
      )}

      <Stack spacing={3}>
        {reviews.map((summary) => {
          const { review, draft_version: draft, base_version: base } = summary;
          const statusColors = STATUS_BADGES[review.status as ReviewStatus];
          const decisionCount = review.decisions.length;
          const isDeletionReview = !review.draft_version_id;
          const reviewerBadges = review.reviewer_ids.map((id: string) => (
            <Badge
              key={id}
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
              title="Double-click to search by this reviewer"
              onDoubleClick={() => goToAuthor(id)}
            >
              @{id.toLowerCase()}
            </Badge>
          ));

          return (
            <Card
              key={review.id}
              bg="github.bg.primary"
              border="1px solid"
              borderColor="github.border.default"
              transition="all 0.2s ease"
              _hover={{ borderColor: "github.border.emphasis", transform: "translateY(-1px)" }}
            >
              <CardHeader borderBottom="1px solid" borderColor="github.border.default" py={3}>
                <Flex justify="space-between" align={{ base: "flex-start", md: "center" }} gap={4} direction={{ base: "column", md: "row" }}>
                  <Stack spacing={1} flex={1} minW={0}>
                    <HStack spacing={2}>
                      <Heading size="sm" fontWeight={600} color="github.accent.fg" noOfLines={1}>
                        <Link to={`/review/${review.id}`}>{review.title || draft.title}</Link>
                      </Heading>
                      {isDeletionReview && (() => {
                        const rtype = (review.type || "").toLowerCase();
                        if (rtype === "restore") {
                          return (
                            <Badge colorScheme="green" fontSize="2xs" px={2} py={0.5}>
                              RESTORE
                            </Badge>
                          );
                        }
                        // fallback to title parsing for older reviews
                        if ((review.title || "").toLowerCase().startsWith("restore:")) {
                          return (
                            <Badge colorScheme="green" fontSize="2xs" px={2} py={0.5}>
                              RESTORE
                            </Badge>
                          );
                        }
                        return (
                          <Badge colorScheme="red" fontSize="2xs" px={2} py={0.5}>
                            DELETION
                          </Badge>
                        );
                      })()}
                    </HStack>
                    <Text fontSize="xs" color="github.fg.muted">
                      Updated {dayjs(review.updated_at).format("MMM D, YYYY h:mm A")} · Note {review.note_id}
                    </Text>
                  </Stack>
                  <HStack spacing={3} align="center" flexShrink={0}>
                    <Badge
                      fontSize="2xs"
                      px={2.5}
                      py={0.5}
                      borderRadius="full"
                      bg={statusColors.bg}
                      color={statusColors.color}
                      textTransform="uppercase"
                      letterSpacing="wide"
                    >
                      {statusColors.label}
                    </Badge>
                    <Button size="sm" variant="secondary" onClick={() => navigate(`/review/${review.id}`)}>
                      View review
                    </Button>
                  </HStack>
                </Flex>
              </CardHeader>
              <CardBody>
                <Stack spacing={3} fontSize="sm">
                  {review.description && (
                    <Text color="github.fg.default">{review.description}</Text>
                  )}
                  <Flex gap={4} direction={{ base: "column", md: "row" }}>
                    <Stack spacing={1} flex={1} minW={0}>
                      <Text fontSize="2xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wide" fontWeight={600}>
                        Draft version
                      </Text>
                      <Text>
                        v{draft.version_index} · Submitted {dayjs(draft.created_at).format("MMM D, YYYY h:mm A")}
                      </Text>
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
                          onDoubleClick={() => goToAuthor(draft.created_by)}
                        >
                          @{draft.created_by.toLowerCase()}
                        </Badge>
                        {draft.tags.slice(0, 5).map((tag: string) => (
                          <Badge
                            key={tag}
                            fontSize="2xs"
                            px={2}
                            py={0.5}
                            borderRadius="full"
                            bg="teal.100"
                            color="teal.700"
                            textTransform="lowercase"
                            cursor="pointer"
                            title="Double-click to search by this tag"
                            onDoubleClick={() => goToTag(tag)}
                          >
                            {tag.toLowerCase()}
                          </Badge>
                        ))}
                      </HStack>
                    </Stack>
                    <Stack spacing={1} flex={1} minW={0}>
                      <Text fontSize="2xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wide" fontWeight={600}>
                        Base version
                      </Text>
                      {base ? (
                        <Text>
                          v{base.version_index} · Published {dayjs(base.created_at).format("MMM D, YYYY h:mm A")}
                        </Text>
                      ) : (
                        <Text color="github.fg.muted">No published baseline – this is the first version.</Text>
                      )}
                    </Stack>
                  </Flex>
                  <Flex wrap="wrap" gap={2} align="center">
                    <Text fontSize="2xs" color="github.fg.muted" fontWeight={600} textTransform="uppercase">
                      Reviewers
                    </Text>
                    {reviewerBadges.length > 0 ? reviewerBadges : <Text fontSize="xs" color="github.fg.muted">Unassigned</Text>}
                  </Flex>
                  <HStack spacing={4} fontSize="xs" color="github.fg.muted">
                    <Tooltip label="Approvals recorded" placement="top">
                      <HStack spacing={1}>
                        <Icon as={MdOutlineRateReview} boxSize={4} />
                        <Text>{review.approvals_count} approvals</Text>
                      </HStack>
                    </Tooltip>
                    <Text>{review.change_requests_count} change requests</Text>
                    <Text>{decisionCount} total responses</Text>
                  </HStack>
                </Stack>
              </CardBody>
            </Card>
          );
        })}
      </Stack>
    </Stack>
  );
}
