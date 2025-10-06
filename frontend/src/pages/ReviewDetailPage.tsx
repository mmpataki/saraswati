import { ChangeEvent, useMemo, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Badge,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Flex,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  HStack,
  Icon,
  Input,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Spinner,
  Stack,
  Text,
  Textarea,
  useDisclosure,
  useToast
} from "@chakra-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import MDEditor from "@uiw/react-md-editor";
import dayjs from "dayjs";
import { useNavigate, useParams } from "react-router-dom";
import {
  FiAlertTriangle,
  FiCheckCircle,
  FiGitMerge,
  FiMessageCircle,
  FiRefreshCw,
  FiSend,
  FiXCircle
} from "react-icons/fi";

import { api } from "../api/client";
import { VersionDiff } from "../components/VersionDiff";
import { useAuth } from "../context/AuthContext";
import {
  NoteResponse,
  ReviewDecision,
  ReviewDecisionResponse,
  ReviewDetailResponse,
  ReviewEventResponse,
  ReviewStatus
} from "../types";

const STATUS_BADGES: Record<ReviewStatus, { bg: string; color: string; label: string }> = {
  open: { bg: "github.accent.subtle", color: "github.accent.fg", label: "Open" },
  changes_requested: { bg: "orange.100", color: "orange.800", label: "Changes requested" },
  merged: { bg: "green.100", color: "green.800", label: "Committed" },
  closed: { bg: "gray.200", color: "gray.700", label: "Closed" }
};

const EVENT_META: Record<string, { label: string; icon: typeof FiMessageCircle; color: string }> = {
  submitted: { label: "Submitted for review", icon: FiSend, color: "github.accent.fg" },
  comment: { label: "Commented", icon: FiMessageCircle, color: "github.fg.default" },
  approved: { label: "Approved", icon: FiCheckCircle, color: "green.600" },
  changes_requested: { label: "Requested changes", icon: FiAlertTriangle, color: "orange.600" },
  merged: { label: "Committed", icon: FiGitMerge, color: "green.600" },
  closed: { label: "Closed", icon: FiXCircle, color: "gray.600" },
  reopened: { label: "Reopened", icon: FiRefreshCw, color: "github.accent.fg" },
  updated: { label: "Updated", icon: FiRefreshCw, color: "github.fg.muted" }
};

const DECISION_META: Record<ReviewDecision | "pending", { label: string; bg: string; color: string }> = {
  approved: { label: "Approved", bg: "green.100", color: "green.800" },
  changes_requested: { label: "Changes requested", bg: "orange.100", color: "orange.800" },
  commented: { label: "Commented", bg: "blue.100", color: "blue.800" },
  pending: { label: "Pending", bg: "gray.200", color: "gray.700" }
};

const formatTags = (tags: string[]): string[] => tags.map((tag) => tag.toLowerCase());

const buildDiffSource = (note?: Pick<NoteResponse, "title" | "tags" | "content"> | null): string => {
  if (!note) {
    return "";
  }
  const tags = formatTags(note.tags).join(", ");
  return `Title: ${note.title || ""}\nTags: ${tags}\n\n${note.content || ""}`;
};

const normalizeId = (value: string | null | undefined): string => (value ? value.toLowerCase() : "");

const parseReviewerInput = (value: string): string[] =>
  Array.from(
    new Set(
      value
        .split(/[\s,]+/)
        .map((entry) => entry.trim().toLowerCase())
        .filter((entry) => entry.length > 0)
    )
  );

export function ReviewDetailPage(): JSX.Element {
  const { reviewId = "" } = useParams<{ reviewId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const [comment, setComment] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const { isOpen: isEditOpen, onOpen: onEditOpen, onClose: onEditClose } = useDisclosure();
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editReviewers, setEditReviewers] = useState("");

  const normalizedUserId = normalizeId(user?.id);

  const detailQuery = useQuery<ReviewDetailResponse>(
    ["review-detail", reviewId],
    async () => {
      const { data } = await api.get<ReviewDetailResponse>(`/reviews/${reviewId}`);
      return data;
    },
    {
      enabled: Boolean(reviewId)
    }
  );

  const invalidateReviewData = () => {
    queryClient.invalidateQueries(["review-detail", reviewId]);
    queryClient.invalidateQueries({ queryKey: ["reviews"] });
  };

  const canSubmit = Boolean(comment.trim());

  const handleSuccess = (message: string) => {
    toast({ title: message, status: "success", duration: 3000, isClosable: true });
    setComment("");
    invalidateReviewData();
  };

  const handleError = (message: string) => {
    toast({ title: message, status: "error", duration: 3000, isClosable: true });
  };

  const commentMutation = useMutation(
    async () => {
      await api.post(`/reviews/${reviewId}/comment`, { message: comment.trim() });
    },
    {
      onSuccess: () => handleSuccess("Comment posted"),
      onError: () => handleError("Failed to post comment")
    }
  );

  const approveMutation = useMutation(
    async () => {
      await api.post(`/reviews/${reviewId}/approve`, { comment: comment.trim() || undefined });
    },
    {
      onSuccess: () => handleSuccess("Approved"),
      onError: () => handleError("Failed to approve")
    }
  );

  const requestChangesMutation = useMutation(
    async () => {
      await api.post(`/reviews/${reviewId}/request-changes`, { comment: comment.trim() || undefined });
    },
    {
      onSuccess: () => handleSuccess("Requested changes"),
      onError: () => handleError("Failed to request changes")
    }
  );

  const mergeMutation = useMutation(
    async () => {
      await api.post(`/reviews/${reviewId}/merge`, { comment: comment.trim() || undefined });
    },
    {
      onSuccess: () => handleSuccess("Review committed"),
      onError: () => handleError("Failed to commit review")
    }
  );

  const closeMutation = useMutation(
    async () => {
      await api.post(`/reviews/${reviewId}/close`, { comment: comment.trim() || undefined });
    },
    {
      onSuccess: () => handleSuccess("Review closed"),
      onError: () => handleError("Failed to close review")
    }
  );

  const reopenMutation = useMutation(
    async () => {
      await api.post(`/reviews/${reviewId}/reopen`, { comment: comment.trim() || undefined });
    },
    {
      onSuccess: () => handleSuccess("Review reopened"),
      onError: () => handleError("Failed to reopen review")
    }
  );

  const updateReviewMutation = useMutation(
    async (payload: { title?: string; description?: string; reviewerIds?: string[] }) => {
      await api.patch(`/reviews/${reviewId}`, {
        title: payload.title,
        description: payload.description,
        reviewer_ids: payload.reviewerIds
      });
    },
    {
      onSuccess: () => {
        toast({ title: "Review updated", status: "success", duration: 3000, isClosable: true });
        invalidateReviewData();
        onEditClose();
      },
      onError: () => handleError("Failed to update review")
    }
  );

  const detail = detailQuery.data;
  const review = detail?.review ?? null;
  const draftVersion = detail?.draft_version ?? null;
  const baseVersion = detail?.base_version ?? null;
  const events: ReviewEventResponse[] = detail?.events ?? [];

  const timeline = useMemo(
    () =>
      [...events].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [events]
  );

  const reviewerIds: string[] = review?.reviewer_ids ?? [];
  const decisions: ReviewDecisionResponse[] = review?.decisions ?? [];
  const decisionsByUser = useMemo(
    () =>
      new Map<string, ReviewDecisionResponse>(
        decisions.map((decision) => [decision.user_id, decision] as const)
      ),
    [decisions]
  );
  const parsedEditReviewers = useMemo(() => parseReviewerInput(editReviewers), [editReviewers]);
  const normalizedReviewerIds = useMemo(() => reviewerIds.map(normalizeId), [reviewerIds]);
  const parsedEditReviewerIdsNormalized = useMemo(
    () => parsedEditReviewers.map(normalizeId).filter((value) => value.length > 0),
    [parsedEditReviewers]
  );
  const currentReviewTitle = review?.title || draftVersion?.title || "";
  const currentReviewDescription = review?.description ?? "";
  const hasEditChanges = useMemo(() => {
    if (!review || !draftVersion) {
      return false;
    }
    const nextTitle = editTitle.trim();
    const nextDescription = editDescription.trim();
    if (nextTitle !== currentReviewTitle || nextDescription !== currentReviewDescription) {
      return true;
    }
    if (parsedEditReviewerIdsNormalized.length !== normalizedReviewerIds.length) {
      return true;
    }
    return parsedEditReviewerIdsNormalized.some((value, index) => value !== normalizedReviewerIds[index]);
  }, [
    review,
    draftVersion,
    editTitle,
    editDescription,
    currentReviewTitle,
    currentReviewDescription,
    parsedEditReviewerIdsNormalized,
    normalizedReviewerIds
  ]);
  const canSubmitEdit = parsedEditReviewerIdsNormalized.length > 0 && hasEditChanges;

  const status = (review?.status ?? "open") as ReviewStatus;
  const isReviewer = reviewerIds.map(normalizeId).includes(normalizedUserId);
  const authorAffinities = [review?.created_by, draftVersion?.created_by, draftVersion?.submitted_by]
    .map(normalizeId)
    .filter((value) => value.length > 0);
  const isAuthor = authorAffinities.includes(normalizedUserId);

  const canApprove = Boolean(review) && isReviewer && !isAuthor && status !== "merged" && status !== "closed";
  const canRequestChanges = Boolean(review) && isReviewer && status !== "merged";
  const canMerge = Boolean(review) && isReviewer && !isAuthor && status === "open";
  const canClose = Boolean(review) && isAuthor && status !== "closed" && status !== "merged";
  const canReopen = Boolean(review) && isAuthor && status === "closed";
  const canComment = Boolean(user);

  const diffBase = buildDiffSource(baseVersion);
  const diffDraft = buildDiffSource(draftVersion);

  if (detailQuery.isLoading) {
    return (
      <Flex justify="center" align="center" minH="50vh">
        <Spinner thickness="3px" color="github.fg.muted" />
      </Flex>
    );
  }

  if (detailQuery.isError || !review || !draftVersion) {
    return (
      <Stack spacing={4}>
        <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <CardBody>
            <Heading size="sm" fontWeight={600} mb={1}>
              Review not found
            </Heading>
            <Text fontSize="sm" color="github.fg.muted">
              We couldn't load this review. It may have been removed or you might not have access.
            </Text>
            <Button mt={3} size="sm" variant="secondary" onClick={() => navigate(-1)}>
              Go back
            </Button>
          </CardBody>
        </Card>
      </Stack>
    );
  }

  const openEditReview = () => {
    setEditTitle(currentReviewTitle);
    setEditDescription(currentReviewDescription);
    setEditReviewers(reviewerIds.join(", "));
    onEditOpen();
  };

  const handleReviewUpdate = () => {
    const trimmedTitle = editTitle.trim();
    const trimmedDescription = editDescription.trim();
    const reviewersChanged =
      parsedEditReviewerIdsNormalized.length !== normalizedReviewerIds.length ||
      parsedEditReviewerIdsNormalized.some((value, index) => value !== normalizedReviewerIds[index]);

    updateReviewMutation.mutate({
      title: trimmedTitle !== currentReviewTitle ? trimmedTitle : undefined,
      description: trimmedDescription !== currentReviewDescription ? trimmedDescription : undefined,
      reviewerIds: reviewersChanged ? parsedEditReviewers : undefined,
    });
  };

  const statusColors = STATUS_BADGES[status];
  const canEditReview = isAuthor && status !== "merged" && status !== "closed";

  return (
    <>
      <Stack spacing={6}>
      <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
        <CardBody>
          <Flex
            direction={{ base: "column", md: "row" }}
            align={{ base: "flex-start", md: "center" }}
            justify="space-between"
            gap={4}
          >
            <Stack spacing={1} flex={1} minW={0}>
              <Heading size="md" fontWeight={600} noOfLines={2}>
                {review.title || draftVersion.title}
              </Heading>
              <Text fontSize="sm" color="github.fg.muted">
                Note {review.note_id} · Draft v{draftVersion.version_index} · Updated {dayjs(review.updated_at).format("MMM D, YYYY h:mm A")}
              </Text>
              {review.description && (
                <Text fontSize="sm" color="github.fg.default">{review.description}</Text>
              )}
            </Stack>
            <Stack spacing={3} align={{ base: "flex-start", md: "flex-end" }}>
              <Badge
                fontSize="xs"
                px={3}
                py={1}
                borderRadius="full"
                bg={statusColors.bg}
                color={statusColors.color}
                textTransform="uppercase"
                letterSpacing="wide"
              >
                {statusColors.label}
              </Badge>
              <HStack spacing={2} flexWrap={{ base: "wrap", md: "nowrap" }}>
                {canEditReview && (
                  <Button size="sm" variant="primary" onClick={openEditReview}>
                    Edit review
                  </Button>
                )}
                <Button size="sm" variant="secondary" onClick={() => navigate(`/note/${review.note_id}`)}>
                  View note
                </Button>
                <Button size="sm" variant="secondary" onClick={() => navigate(`/note/${review.note_id}/history`)}>
                  History
                </Button>
              </HStack>
            </Stack>
          </Flex>

          <Divider my={4} borderColor="github.border.default" />

          <Grid templateColumns={{ base: "1fr", md: "repeat(4, minmax(0, 1fr))" }} gap={3}>
            <GridItem>
              <Text fontSize="2xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wide" fontWeight={600}>
                Author
              </Text>
              <Badge
                display="inline-flex"
                alignItems="center"
                gap={1}
                fontSize="xs"
                px={2}
                py={0.5}
                borderRadius="full"
                bg="gray.200"
                color="gray.700"
                textTransform="lowercase"
              >
                @{draftVersion.created_by.toLowerCase()}
              </Badge>
            </GridItem>
            <GridItem>
              <Text fontSize="2xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wide" fontWeight={600}>
                Submitted by
              </Text>
              {draftVersion.submitted_by ? (
                <Badge
                  display="inline-flex"
                  alignItems="center"
                  gap={1}
                  fontSize="xs"
                  px={2}
                  py={0.5}
                  borderRadius="full"
                  bg="gray.200"
                  color="gray.700"
                  textTransform="lowercase"
                >
                  @{draftVersion.submitted_by.toLowerCase()}
                </Badge>
              ) : (
                <Text fontSize="xs" color="github.fg.muted">—</Text>
              )}
            </GridItem>
            <GridItem>
              <Text fontSize="2xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wide" fontWeight={600}>
                Reviewers
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                {reviewerIds.length > 0 ? (
                  reviewerIds.map((id) => (
                    <Badge
                      key={id}
                      fontSize="xs"
                      px={2}
                      py={0.5}
                      borderRadius="full"
                      bg="gray.200"
                      color="gray.700"
                      textTransform="lowercase"
                    >
                      @{id.toLowerCase()}
                    </Badge>
                  ))
                ) : (
                  <Text fontSize="xs" color="github.fg.muted">Unassigned</Text>
                )}
              </HStack>
            </GridItem>
            <GridItem>
              <Text fontSize="2xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wide" fontWeight={600}>
                Decisions logged
              </Text>
              <Text fontSize="xs" color="github.fg.default">
                {review.approvals_count} approvals · {review.change_requests_count} change requests
              </Text>
            </GridItem>
          </Grid>
          {status === "changes_requested" && isAuthor && (
            <Box mt={4}>
              <Alert status="warning" variant="left-accent" alignItems="flex-start">
                <AlertIcon />
                <Stack spacing={1} flex={1} minW={0}>
                  <AlertTitle fontSize="sm">Reviewers requested changes</AlertTitle>
                  <AlertDescription fontSize="sm" color="orange.900">
                    Update the draft from the authoring page and submit again when you&apos;re ready—resubmitting reopens this same review so the existing discussion stays together.
                  </AlertDescription>
                  <Button size="xs" variant="secondary" onClick={() => navigate(`/edit/${review.note_id}`)} width={{ base: "full", sm: "auto" }}>
                    Edit draft
                  </Button>
                </Stack>
              </Alert>
            </Box>
          )}
        </CardBody>
      </Card>

      <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
        <CardHeader borderBottom="1px solid" borderColor="github.border.default" py={2}>
          <Flex justify="space-between" align="center">
            <Heading size="sm" fontWeight={600}>
              Changes
            </Heading>
            <ButtonGroup size="xs" variant="outline" isAttached>
              <Button
                onClick={() => setShowDiff(false)}
                bg={!showDiff ? "github.accent.subtle" : "transparent"}
                color={!showDiff ? "github.accent.fg" : "github.fg.default"}
                borderColor="github.border.default"
              >
                Preview
              </Button>
              <Button
                onClick={() => setShowDiff(true)}
                bg={showDiff ? "github.accent.subtle" : "transparent"}
                color={showDiff ? "github.accent.fg" : "github.fg.default"}
                borderColor="github.border.default"
              >
                Diff
              </Button>
            </ButtonGroup>
          </Flex>
        </CardHeader>
        <CardBody>
          {showDiff ? (
            <VersionDiff oldContent={diffBase} newContent={diffDraft} />
          ) : (
            <Box data-color-mode="light" fontSize="sm">
              <MDEditor.Markdown source={draftVersion.content} style={{ fontSize: "0.875rem" }} />
            </Box>
          )}
        </CardBody>
      </Card>

      <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
        <CardHeader borderBottom="1px solid" borderColor="github.border.default" py={2}>
          <Heading size="sm" fontWeight={600}>
            Event timeline
          </Heading>
        </CardHeader>
        <CardBody>
          <Stack spacing={3}>
            {timeline.length === 0 && (
              <Text fontSize="sm" color="github.fg.muted">
                No activity yet.
              </Text>
            )}
            {timeline.map((event) => {
              const meta = EVENT_META[event.event_type] ?? EVENT_META.comment;
              const metadataEntries = Object.entries(event.metadata ?? {});
              return (
                <Stack
                  key={event.id ?? `${event.event_type}-${event.created_at}`}
                  spacing={1}
                  borderLeft="2px solid"
                  borderColor="github.border.default"
                  pl={3}
                >
                  <HStack spacing={2} align="center">
                    <Icon as={meta.icon} color={meta.color} boxSize={4} />
                    <Text fontWeight={600} fontSize="sm" color={meta.color}>
                      {meta.label}
                    </Text>
                    <Text fontSize="xs" color="github.fg.muted">
                      @{event.author_id} · {dayjs(event.created_at).format("MMM D, YYYY h:mm A")}
                    </Text>
                  </HStack>
                  {event.message && (
                    <Text fontSize="sm" color="github.fg.default">
                      {event.message}
                    </Text>
                  )}
                  {metadataEntries.length > 0 && (
                    <Text fontSize="xs" color="github.fg.muted">
                      {metadataEntries.map(([key, value]) => `${key}: ${value}`).join(" · ")}
                    </Text>
                  )}
                </Stack>
              );
            })}
          </Stack>
        </CardBody>
      </Card>

      <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
        <CardHeader borderBottom="1px solid" borderColor="github.border.default" py={2}>
          <Heading size="sm" fontWeight={600}>
            Reviewer decisions
          </Heading>
        </CardHeader>
        <CardBody>
          <Stack spacing={3}>
            {reviewerIds.length === 0 && (
              <Text fontSize="sm" color="github.fg.muted">
                No reviewers assigned.
              </Text>
            )}
            {reviewerIds.map((id) => {
              const decision = decisionsByUser.get(id);
              const decisionMeta = DECISION_META[decision?.decision ?? "pending"];
              return (
                <Flex key={id} justify="space-between" align="center" gap={2}>
                  <Stack spacing={0}>
                    <Text fontWeight={600} fontSize="sm">
                      @{id.toLowerCase()}
                    </Text>
                    {decision?.comment && (
                      <Text fontSize="sm" color="github.fg.default">
                        {decision.comment}
                      </Text>
                    )}
                    {decision && (
                      <Text fontSize="xs" color="github.fg.muted">
                        Updated {dayjs(decision.updated_at).format("MMM D, YYYY h:mm A")}
                      </Text>
                    )}
                  </Stack>
                  <Badge
                    fontSize="xs"
                    px={2}
                    py={0.5}
                    borderRadius="full"
                    bg={decisionMeta.bg}
                    color={decisionMeta.color}
                    textTransform="uppercase"
                    letterSpacing="wide"
                  >
                    {decisionMeta.label}
                  </Badge>
                </Flex>
              );
            })}
          </Stack>
        </CardBody>
      </Card>

      {canComment && (
        <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <CardHeader borderBottom="1px solid" borderColor="github.border.default" py={2}>
            <Heading size="sm" fontWeight={600}>
              Respond to this review
            </Heading>
          </CardHeader>
          <CardBody>
            <Stack spacing={3}>
              <Textarea
                placeholder="Share feedback or a decision comment..."
                value={comment}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setComment(event.target.value)}
                bg="github.bg.primary"
                borderColor="github.border.default"
                _hover={{ borderColor: "github.border.emphasis" }}
                _focus={{
                  borderColor: "github.border.emphasis",
                  boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)"
                }}
                rows={3}
                fontSize="sm"
              />
              <HStack spacing={2} flexWrap="wrap">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => commentMutation.mutate()}
                  isDisabled={!canSubmit || commentMutation.isLoading}
                  isLoading={commentMutation.isLoading}
                >
                  Comment
                </Button>
                {canApprove && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => approveMutation.mutate()}
                    isLoading={approveMutation.isLoading}
                  >
                    Approve
                  </Button>
                )}
                {canRequestChanges && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => requestChangesMutation.mutate()}
                    isLoading={requestChangesMutation.isLoading}
                  >
                    Request changes
                  </Button>
                )}
                {canMerge && (
                  <Button
                    size="sm"
                    colorScheme="green"
                    onClick={() => mergeMutation.mutate()}
                    isLoading={mergeMutation.isLoading}
                  >
                    Merge
                  </Button>
                )}
                {canClose && (
                  <Button
                    size="sm"
                    colorScheme="gray"
                    onClick={() => closeMutation.mutate()}
                    isLoading={closeMutation.isLoading}
                  >
                    Cancel review
                  </Button>
                )}
                {canReopen && (
                  <Button
                    size="sm"
                    colorScheme="blue"
                    onClick={() => reopenMutation.mutate()}
                    isLoading={reopenMutation.isLoading}
                  >
                    Reopen
                  </Button>
                )}
              </HStack>
              <Text fontSize="xs" color="github.fg.muted">
                Comments are optional for decisions, but required when posting to the timeline.
              </Text>
            </Stack>
          </CardBody>
        </Card>
      )}

      {status === "merged" && (
        <Card bg="github.success.subtle" border="1px solid" borderColor="github.success.emphasis">
          <CardBody>
            <Text fontWeight={600} color="github.success.fg">
              Review committed
            </Text>
            <Text fontSize="sm" color="github.success.fg">
              The drafted changes were published on {dayjs(review.merged_at ?? review.updated_at).format("MMM D, YYYY h:mm A")}.
            </Text>
          </CardBody>
        </Card>
      )}
      </Stack>

      <Modal isOpen={isEditOpen} onClose={onEditClose} isCentered size="lg">
        <ModalOverlay backdropFilter="blur(4px)" />
        <ModalContent bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <ModalHeader>Edit review</ModalHeader>
          <ModalBody>
            <Stack spacing={4}>
              <FormControl isRequired>
                <FormLabel fontSize="sm" fontWeight={600}>
                  Review title
                </FormLabel>
                <Input
                  value={editTitle}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setEditTitle(event.target.value)}
                  placeholder="Enter a concise title"
                  size="sm"
                  bg="github.bg.primary"
                  borderColor="github.border.default"
                  _hover={{ borderColor: "github.border.emphasis" }}
                  _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                />
              </FormControl>
              <FormControl>
                <FormLabel fontSize="sm" fontWeight={600}>
                  Summary / description
                </FormLabel>
                <Textarea
                  value={editDescription}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setEditDescription(event.target.value)}
                  placeholder="Explain what reviewers should focus on"
                  rows={3}
                  fontSize="sm"
                  bg="github.bg.primary"
                  borderColor="github.border.default"
                  _hover={{ borderColor: "github.border.emphasis" }}
                  _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                />
              </FormControl>
              <FormControl isRequired>
                <FormLabel fontSize="sm" fontWeight={600}>
                  Reviewers
                </FormLabel>
                <Input
                  value={editReviewers}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setEditReviewers(event.target.value)}
                  placeholder="alice bob charlie"
                  size="sm"
                  bg="github.bg.primary"
                  borderColor="github.border.default"
                  _hover={{ borderColor: "github.border.emphasis" }}
                  _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                />
              </FormControl>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <HStack spacing={2}>
              <Button variant="ghost" onClick={onEditClose} size="sm">
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleReviewUpdate}
                isDisabled={!canSubmitEdit || updateReviewMutation.isLoading}
                isLoading={updateReviewMutation.isLoading}
              >
                Save changes
              </Button>
            </HStack>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </>
  );
}
