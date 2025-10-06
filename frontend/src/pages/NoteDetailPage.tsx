import { ChangeEvent, useMemo, useState } from "react";
import {
  Badge,
  Box,
  Button,
  ButtonGroup,
  Flex,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  HStack,
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
import { ArrowDownIcon, ArrowUpIcon, AtSignIcon, EditIcon } from "@chakra-ui/icons";
import { MdLocalOffer } from "react-icons/md";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import MDEditor from "@uiw/react-md-editor";
import dayjs from "dayjs";

import { api } from "../api/client";
import { NoteResponse } from "../types";
import { useSearchNavigation } from "../hooks/useSearchNavigation";

export function NoteDetailPage(): JSX.Element {
  const { noteId = "" } = useParams<{ noteId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { goToTag, goToAuthor } = useSearchNavigation();
  const [showDraft, setShowDraft] = useState(false);
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();
  const { isOpen: isRestoreOpen, onOpen: onRestoreOpen, onClose: onRestoreClose } = useDisclosure();
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteReviewers, setDeleteReviewers] = useState("");
  const [restoreReason, setRestoreReason] = useState("");
  const [restoreReviewers, setRestoreReviewers] = useState("");

  const detailQuery = useQuery<NoteResponse>(
    ["note-detail", noteId],
    async () => {
      const { data } = await api.get<NoteResponse>(`/notes/${noteId}`);
      return data;
    },
    {
      enabled: Boolean(noteId)
    }
  );

  const draftQuery = useQuery<NoteResponse>(
    ["note-draft", noteId],
    async () => {
      const history = await api.get<NoteResponse[]>(`/notes/${noteId}/history`);
      const draft = history.data.find((v: NoteResponse) => v.state === "draft");
      if (!draft) throw new Error("No draft found");
      return draft;
    },
    {
      enabled: Boolean(noteId) && showDraft && detailQuery.data?.has_draft === true,
      retry: false
    }
  );

  const voteMutation = useMutation(
    async (action: "upvote" | "downvote") => {
      const { data } = await api.post<NoteResponse>(`/notes/${noteId}/vote`, { action });
      return data;
    },
    {
      onSuccess: (data: NoteResponse) => {
        queryClient.setQueryData(["note-detail", noteId], data);
      }
    }
  );

  const deleteMutation = useMutation(
    async () => {
      const reviewerIds = deleteReviewers
        .split(/[\s,]+/)
        .map((r) => r.trim())
        .filter((r) => r.length > 0);
      await api.delete(`/notes/${noteId}`, {
        data: {
          reason: deleteReason.trim() || undefined,
          reviewer_ids: reviewerIds.length > 0 ? reviewerIds : undefined
        }
      });
    },
    {
      onSuccess: () => {
        toast({
          title: "Deletion review created",
          description: "A review has been created for this note deletion.",
          status: "success",
          duration: 3000,
          isClosable: true
        });
        queryClient.invalidateQueries(["note-detail"]);
        queryClient.invalidateQueries(["reviews"]);
        setDeleteReason("");
        setDeleteReviewers("");
        navigate("/review");
      },
      onError: () => {
        toast({
          title: "Delete request failed",
          description: "Could not create deletion review. Please try again.",
          status: "error",
          duration: 3000,
          isClosable: true
        });
      }
    }
  );

  const note = showDraft && draftQuery.data ? draftQuery.data : detailQuery.data;
  const hasDraft = detailQuery.data?.has_draft === true;

  const metadata = useMemo((): Array<{ label: string; value: string }> => {
    if (!note) {
      return [];
    }
    const meta = [
      { label: "State", value: note.state.toUpperCase() },
      { label: "Version", value: `v${note.version_index}` },
      { label: "Created", value: dayjs(note.created_at).format("MMM D, YYYY h:mm A") },
      { label: "Author", value: note.created_by },
      { label: "Committed By", value: note.committed_by ?? "—" },
      { label: "Submitted By", value: note.submitted_by ?? "—" },
      { label: "Reviewed By", value: note.reviewed_by ?? "—" }
    ];
    if (note.deleted_at) {
      meta.push({
        label: "Deleted",
        value: `${dayjs(note.deleted_at).format("MMM D, YYYY h:mm A")} by ${note.deleted_by ?? "unknown"}`
      });
    }
    return meta;
  }, [note]);

  if (detailQuery.isLoading) {
    return (
      <Flex justify="center" align="center" minH="50vh">
        <Spinner thickness="3px" color="github.accent.emphasis" />
      </Flex>
    );
  }

  if (!note) {
    return (
      <Box border="1px solid" borderColor="github.border.default" borderRadius="md" bg="github.bg.primary" p={6}>
        <Heading size="sm" mb={2}>Note not found</Heading>
        <Text fontSize="sm" color="github.fg.muted">This note may have been removed or you no longer have access.</Text>
      </Box>
    );
  }

  const handleEdit = () => {
    navigate(`/edit/${note.id}`);
  };

  const handleVote = (action: "upvote" | "downvote") => {
    voteMutation.mutate(action);
  };

  return (
    <Stack spacing={4}>
      <Flex justify="space-between" align={{ base: "stretch", md: "center" }} direction={{ base: "column", md: "row" }} gap={3}>
        {/* Left column: allow this area to shrink and wrap (minWidth=0) so long titles/tags wrap instead of forcing the actions to wrap */}
        <Stack spacing={1.5} flex="1" minW={0}>
          <HStack align="baseline" spacing={3}>
            <Heading size="md" fontWeight={600}>{note.title}</Heading>
            {note.deleted_at && (
              <Badge colorScheme="red" fontSize="xs" px={2} py={1}>
                DELETED
              </Badge>
            )}
          </HStack>

          <HStack spacing={1.5} flexWrap="wrap">
            {note.tags.map((tag: string) => (
              <Badge
                key={tag}
                display="flex"
                alignItems="center"
                gap={1}
                fontSize="2xs"
                px={2}
                py={1}
                borderRadius="full"
                bg="teal.100"
                color="teal.700"
                textTransform="lowercase"
                cursor="pointer"
                title="Double-click to search by this tag"
                onDoubleClick={() => goToTag(tag)}
              >
                <MdLocalOffer size={10} />
                {tag.toLowerCase()}
              </Badge>
            ))}
            {note.state === "draft" && (
              <Badge
                fontSize="2xs"
                px={2}
                py={1}
                borderRadius="full"
                bg="yellow.100"
                color="yellow.800"
                textTransform="lowercase"
              >
                draft
              </Badge>
            )}
            {note.state === "needs_review" && (
              <Badge
                fontSize="2xs"
                px={2}
                py={1}
                borderRadius="full"
                bg="orange.100"
                color="orange.800"
                textTransform="lowercase"
              >
                needs review
              </Badge>
            )}
            {note.state === "approved" && (
              <Badge
                fontSize="2xs"
                px={2}
                py={1}
                borderRadius="full"
                bg="green.100"
                color="green.800"
                textTransform="lowercase"
              >
                approved
              </Badge>
            )}
          </HStack>
        </Stack>
        {/* Actions: keep them on a single row and don't allow wrapping */}
        <HStack spacing={2} align="center" flexWrap="nowrap" flexShrink={0}>
          {hasDraft && (
            <ButtonGroup size="xs" isAttached variant="outline">
              <Button
                onClick={() => setShowDraft(false)}
                bg={!showDraft ? "github.accent.subtle" : "transparent"}
                color={!showDraft ? "github.accent.fg" : "github.fg.default"}
                borderColor="github.border.default"
                _hover={{ bg: !showDraft ? "github.accent.subtle" : "github.bg.secondary" }}
              >
                Published
              </Button>
              <Button
                onClick={() => setShowDraft(true)}
                bg={showDraft ? "github.accent.subtle" : "transparent"}
                color={showDraft ? "github.accent.fg" : "github.fg.default"}
                borderColor="github.border.default"
                _hover={{ bg: showDraft ? "github.accent.subtle" : "github.bg.secondary" }}
              >
                Draft
              </Button>
            </ButtonGroup>
          )}
          {!note.deleted_at ? (
            <Button
              size="xs"
              variant="outline"
              leftIcon={<EditIcon boxSize={3} />}
              onClick={handleEdit}
            >
              Edit
            </Button>
          ) : (
            <Button size="xs" variant="outline" isDisabled leftIcon={<EditIcon boxSize={3} />}>Edit</Button>
          )}
          <Button
            size="xs"
            variant="secondary"
            onClick={() => navigate(`/note/${note.id}/history`)}
          >
            History
          </Button>
          {note.state === "needs_review" && note.active_review_id && (
            <Button
              size="xs"
              variant="outline"
              colorScheme="orange"
              onClick={() => navigate(`/review/${note.active_review_id}`)}
            >
              Go to review
            </Button>
          )}
          {!note.deleted_at && (
            <Button
              size="xs"
              variant="secondary"
              color="github.danger.fg"
              borderColor="github.border.default"
              _hover={{ bg: "github.danger.subtle" }}
              onClick={onDeleteOpen}
            >
              Delete
            </Button>
          )}
          {note.deleted_at && (
            <Button
              size="xs"
              variant="secondary"
              colorScheme="green"
              onClick={onRestoreOpen}
            >
              Restore
            </Button>
          )}
          <Button
            size="xs"
            variant="secondary"
            leftIcon={<ArrowUpIcon boxSize={3} />}
            onClick={() => handleVote("upvote")}
            isLoading={voteMutation.isLoading && voteMutation.variables === "upvote"}
          >
            {note.upvotes}
          </Button>
          <Button
            size="xs"
            variant="secondary"
            leftIcon={<ArrowDownIcon boxSize={3} />}
            onClick={() => handleVote("downvote")}
            isLoading={voteMutation.isLoading && voteMutation.variables === "downvote"}
          >
            {note.downvotes}
          </Button>
        </HStack>
      </Flex>

      {note.deleted_at && (
        <Box mt={3} borderLeft="4px solid" borderColor="red.400" bg="red.50" p={3} borderRadius="md">
          <Text fontSize="sm" color="red.800" fontWeight={600}>
            This note was deleted {dayjs(note.deleted_at).format("MMM D, YYYY h:mm A")} by {note.deleted_by ?? "unknown"}.
          </Text>
          {note.review_comment && (
            <Text mt={2} fontSize="sm" color="red.700">Reason: {note.review_comment}</Text>
          )}
        </Box>
      )}

      <Grid templateColumns={{ base: "1fr", md: "repeat(4, minmax(0, 1fr))" }} gap={2} border="1px solid" borderColor="github.border.default" borderRadius="md" bg="github.bg.primary" p={3}>
        {metadata.map((item) => (
          <GridItem key={item.label}>
            <Text fontSize="2xs" textTransform="uppercase" letterSpacing="wide" color="github.fg.muted" fontWeight={600}>
              {item.label}
            </Text>
            {(item.label.includes("By") || item.label === "Author") && item.value !== "—" ? (
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
                onDoubleClick={() => goToAuthor(item.value)}
              >
                <AtSignIcon boxSize={2.5} />
                {item.value.toLowerCase()}
              </Badge>
            ) : item.label === "State" ? (
              <Badge
                fontSize="2xs"
                px={2}
                py={0.5}
                borderRadius="full"
                bg={item.value === "DRAFT" ? "yellow.100" : item.value === "NEEDS_REVIEW" ? "orange.100" : "green.100"}
                color={item.value === "DRAFT" ? "yellow.800" : item.value === "NEEDS_REVIEW" ? "orange.800" : "green.800"}
                textTransform="lowercase"
              >
                {item.value.toLowerCase().replace("_", " ")}
              </Badge>
            ) : (
              <Text fontSize="xs" color="github.fg.default">{item.value}</Text>
            )}
          </GridItem>
        ))}
        {note.review_comment && (
          <GridItem colSpan={{ base: 1, md: 4 }}>
            <Text fontSize="2xs" textTransform="uppercase" letterSpacing="wide" color="github.fg.muted" fontWeight={600}>
              Review Comment
            </Text>
            <Text fontSize="xs" color="github.fg.default">{note.review_comment}</Text>
          </GridItem>
        )}
      </Grid>

      <Box border="1px solid" borderColor="github.border.default" borderRadius="md" bg="github.bg.primary" p={4}>
        <Box data-color-mode="light" fontSize="sm">
          <MDEditor.Markdown source={note.content} style={{ fontSize: "0.875rem" }} />
        </Box>
      </Box>

      <Modal isOpen={isDeleteOpen} onClose={onDeleteClose} isCentered size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Request Note Deletion</ModalHeader>
          <ModalBody>
            <Stack spacing={4}>
              <Text fontSize="sm" color="github.fg.muted">
                Deleting a note requires review approval. Provide a reason for deletion and assign reviewers.
              </Text>
              <FormControl>
                <FormLabel fontSize="sm" fontWeight={600}>Reason for deletion</FormLabel>
                <Textarea
                  value={deleteReason}
                  onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setDeleteReason(e.target.value)}
                  placeholder="Explain why this note should be deleted..."
                  size="sm"
                  rows={3}
                />
              </FormControl>
              <FormControl>
                <FormLabel fontSize="sm" fontWeight={600}>Reviewers (optional)</FormLabel>
                <Input
                  value={deleteReviewers}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setDeleteReviewers(e.target.value)}
                  placeholder="user1, user2, user3"
                  size="sm"
                />
                <Text fontSize="xs" color="github.fg.muted" mt={1}>
                  Comma-separated list of reviewer usernames
                </Text>
              </FormControl>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" mr={3} onClick={onDeleteClose}>
              Cancel
            </Button>
            <Button
              colorScheme="red"
              onClick={() => {
                deleteMutation.mutate();
                onDeleteClose();
              }}
              isLoading={deleteMutation.isLoading}
            >
              Submit for Review
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <Modal isOpen={isRestoreOpen} onClose={onRestoreClose} isCentered size="lg">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Request Note Restore</ModalHeader>
          <ModalBody>
            <Stack spacing={4}>
              <Text fontSize="sm" color="github.fg.muted">
                Restoring a note requires review approval. Provide a reason for restore and assign reviewers.
              </Text>
              <FormControl>
                <FormLabel fontSize="sm" fontWeight={600}>Reason for restore</FormLabel>
                <Textarea
                  value={restoreReason}
                  onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setRestoreReason(e.target.value)}
                  placeholder="Explain why this note should be restored..."
                  size="sm"
                  rows={3}
                />
              </FormControl>
              <FormControl>
                <FormLabel fontSize="sm" fontWeight={600}>Reviewers (optional)</FormLabel>
                <Input
                  value={restoreReviewers}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setRestoreReviewers(e.target.value)}
                  placeholder="user1, user2, user3"
                  size="sm"
                />
                <Text fontSize="xs" color="github.fg.muted" mt={1}>
                  Comma-separated list of reviewer usernames
                </Text>
              </FormControl>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" mr={3} onClick={onRestoreClose}>
              Cancel
            </Button>
            <Button
              colorScheme="green"
              onClick={async () => {
                const reviewerIds = restoreReviewers
                  .split(/[,\s]+/)
                  .map((r) => r.trim())
                  .filter((r) => r.length > 0);
                try {
                  await api.post(`/notes/${note.id}/restore`, {
                    reason: restoreReason.trim() || undefined,
                    reviewer_ids: reviewerIds.length > 0 ? reviewerIds : undefined
                  });
                  toast({
                    title: "Restore review created",
                    description: "A review has been created to restore this note.",
                    status: "success",
                    duration: 3000,
                    isClosable: true
                  });
                  queryClient.invalidateQueries(["note-detail"]);
                  queryClient.invalidateQueries(["reviews"]);
                  setRestoreReason("");
                  setRestoreReviewers("");
                  onRestoreClose();
                  navigate("/review");
                } catch (err) {
                  toast({
                    title: "Restore request failed",
                    description: "Could not create restore review. Please try again.",
                    status: "error",
                    duration: 3000,
                    isClosable: true
                  });
                }
              }}
            >
              Submit for Review
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Stack>
  );
}
