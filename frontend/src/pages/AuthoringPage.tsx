import { ChangeEvent, KeyboardEvent, MouseEvent as ReactMouseEvent, useCallback, useEffect, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Box,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  CloseButton,
  Flex,
  FormControl,
  FormHelperText,
  FormLabel,
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
import { useNavigate, useParams } from "react-router-dom";
import { EditIcon } from "@chakra-ui/icons";
import dayjs from "dayjs";

import { api } from "../api/client";
import { NoteResponse, ReviewDetailResponse, ReviewSubmissionResponse } from "../types";
import { useSearchNavigation } from "../hooks/useSearchNavigation";

export function AuthoringPage(): JSX.Element {
  const toast = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { noteId: routeNoteId } = useParams<{ noteId?: string }>();
  const { goToTag } = useSearchNavigation();

  const isNew = !routeNoteId || routeNoteId === "new";
  const activeNoteId = !isNew ? routeNoteId ?? "" : "";

  const [title, setTitle] = useState("");
  const [content, setContent] = useState<string | undefined>("## Start writing");
  const [tags, setTags] = useState<string[]>(["knowledge"]);
  const [tagInput, setTagInput] = useState("");
  const [draftVersion, setDraftVersion] = useState<NoteResponse | null>(null);
  const [initializedExisting, setInitializedExisting] = useState(false);
  const { isOpen: isDiscardOpen, onOpen: onDiscardOpen, onClose: onDiscardClose } = useDisclosure();
  const { isOpen: isReviewOpen, onOpen: onReviewOpen, onClose: onReviewClose } = useDisclosure();
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewSummary, setReviewSummary] = useState("");
  const [reviewersText, setReviewersText] = useState("");

  const parseReviewerInput = useCallback((value: string) => {
    return value
      .split(/[\s,]+/)
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0);
  }, []);

  const draftsQuery = useQuery<NoteResponse[]>(["my-drafts"], async () => {
    const { data } = await api.get<NoteResponse[]>("/notes/drafts");
    return data;
  });

  const detailQuery = useQuery<NoteResponse>(
    ["authoring-detail", activeNoteId],
    async () => {
      const { data } = await api.get<NoteResponse>(`/notes/${activeNoteId}`);
      return data;
    },
    {
      enabled: Boolean(activeNoteId)
    }
  );

  const activeReviewId = detailQuery.data?.active_review_id ?? null;
  const activeReviewStatus = detailQuery.data?.active_review_status ?? null;
  const showChangesRequestedAlert = !isNew && activeReviewStatus === "changes_requested" && Boolean(activeReviewId);

  const activeReviewQuery = useQuery<ReviewDetailResponse>(
    ["review-detail", activeReviewId],
    async () => {
      const { data } = await api.get<ReviewDetailResponse>(`/reviews/${activeReviewId}`);
      return data;
    },
    {
      enabled: Boolean(activeReviewId)
    }
  );

  useEffect(() => {
    if (isNew) {
      setTitle("");
      setContent("## Start writing");
      setTags(["knowledge"]);
      setTagInput("");
      setDraftVersion(null);
      setInitializedExisting(false);
      return;
    }

    setDraftVersion(null);
    setInitializedExisting(false);
    setTagInput("");
  }, [isNew, activeNoteId]);

  useEffect(() => {
    if (!isNew && detailQuery.data && !initializedExisting) {
      const note = detailQuery.data;
      setTitle(note.title);
      setContent(note.content);
      setTags(note.tags.map((tag: string) => tag.toLowerCase()));
      setTagInput("");
      setInitializedExisting(true);
    }
  }, [isNew, detailQuery.data, initializedExisting]);

  useEffect(() => {
    if (isNew || !detailQuery.data) {
      return;
    }
    if (detailQuery.data.state === "draft" && detailQuery.data.version_id && detailQuery.data.version_id !== draftVersion?.version_id) {
      setDraftVersion(detailQuery.data);
    }
  }, [isNew, detailQuery.data, draftVersion?.version_id]);

  useEffect(() => {
    if (isNew || !draftsQuery.data) {
      return;
    }
  const match = draftsQuery.data.find((entry: NoteResponse) => entry.id === activeNoteId);
    if (match && match.version_id !== draftVersion?.version_id) {
      setDraftVersion(match);
    }
  }, [isNew, draftsQuery.data, activeNoteId, draftVersion?.version_id]);

  const createMutation = useMutation(
    async () => {
      const { data } = await api.post<NoteResponse>("/notes", {
        title,
        content,
        tags
      });
      return data;
    },
    {
      onSuccess: (data: NoteResponse) => {
        toast({ title: "Draft created", status: "success", duration: 3000, isClosable: true });
        setDraftVersion(data);
        queryClient.invalidateQueries(["my-drafts"]);
        navigate(`/edit/${data.id}`);
      }
    }
  );

  const updateMutation = useMutation(
    async () => {
      if (!activeNoteId) {
        throw new Error("Missing note id for update");
      }
      const { data } = await api.post<NoteResponse>(`/notes/${activeNoteId}/draft`, {
        title,
        content,
        tags
      });
      return data;
    },
    {
      onSuccess: (data: NoteResponse) => {
        toast({ title: "Draft saved", status: "success", duration: 3000, isClosable: true });
        setDraftVersion(data);
        queryClient.invalidateQueries(["my-drafts"]);
        queryClient.invalidateQueries(["authoring-detail", activeNoteId]);
      }
    }
  );

  type ReviewSubmitMetadata = {
    title?: string;
    summary?: string;
    description?: string;
    reviewerIds: string[];
  };

  const submitMutation = useMutation(
    async (metadata: ReviewSubmitMetadata) => {
      if (!draftVersion) {
        throw new Error("Missing draft version for submission");
      }
      const { data } = await api.post<ReviewSubmissionResponse>(
        `/notes/versions/${draftVersion.version_id}/submit`,
        {
          title: metadata.title,
          summary: metadata.summary,
          description: metadata.description,
          reviewer_ids: metadata.reviewerIds,
        }
      );
      return data;
    },
    {
      onSuccess: (data: ReviewSubmissionResponse) => {
        toast({ title: "Submitted for review", status: "success", duration: 3000, isClosable: true });
        setDraftVersion(data.version);
        queryClient.invalidateQueries(["my-drafts"]);
        queryClient.invalidateQueries({ queryKey: ["reviews"] });
        if (activeNoteId) {
          queryClient.invalidateQueries(["authoring-detail", activeNoteId]);
          queryClient.invalidateQueries(["note-detail", activeNoteId]);
          queryClient.invalidateQueries(["note-history", activeNoteId]);
        }
        onReviewClose();
        navigate(`/review/${data.review.id}`);
      },
      onError: () => {
        toast({ title: "Failed to submit review", status: "error", duration: 3000, isClosable: true });
      },
    }
  );

  const handleSave = () => {
    if (isNew) {
      createMutation.mutate();
    } else {
      updateMutation.mutate();
    }
  };

  const handleSubmit = async () => {
    if (!draftVersion) {
      return;
    }

    let activeReviewData = activeReviewQuery.data;
    if (activeReviewId && !activeReviewData) {
      const result = await activeReviewQuery.refetch();
      activeReviewData = result.data;
    }

    const existingReview = activeReviewData?.review;

    setReviewTitle(existingReview?.title || title || "Review request");
    setReviewSummary(existingReview?.description ?? "");
    setReviewersText(existingReview?.reviewer_ids?.join(" ") ?? "");
    onReviewOpen();
  };

  const handleConfirmReview = () => {
    if (!draftVersion) {
      return;
    }
    const reviewerIds = Array.from(new Set(parseReviewerInput(reviewersText)));
    submitMutation.mutate({
      title: reviewTitle.trim() || undefined,
      summary: reviewSummary.trim() || undefined,
      reviewerIds
    });
  };

  const discardMutation = useMutation(
    async () => {
      if (!activeNoteId) {
        throw new Error("Missing note id for discard");
      }
      await api.delete(`/notes/${activeNoteId}/draft`);
    },
    {
      onSuccess: async () => {
        toast({ title: "Draft discarded", status: "success", duration: 3000, isClosable: true });
        setDraftVersion(null);
        queryClient.invalidateQueries(["my-drafts"]);
        queryClient.invalidateQueries({ queryKey: ["reviews"] });
        if (activeNoteId) {
          queryClient.invalidateQueries(["authoring-detail", activeNoteId]);
          queryClient.invalidateQueries(["note-detail", activeNoteId]);
          queryClient.invalidateQueries(["note-history", activeNoteId]);
        }
        const hasApprovedBase = detailQuery.data && detailQuery.data.state !== "draft";
        if (activeNoteId && hasApprovedBase) {
          navigate(`/note/${activeNoteId}`);
        } else {
          navigate("/search");
        }
      },
      onError: () => {
        toast({ title: "Failed to discard draft", status: "error", duration: 3000, isClosable: true });
      }
    }
  );

  const loadDraft = (draft: NoteResponse) => {
    navigate(`/edit/${draft.id}`);
  };

  const addTag = () => {
    const value = tagInput.trim().toLowerCase();
    if (!value || tags.includes(value)) {
      setTagInput("");
      return;
    }
    setTags((existing) => [...existing, value]);
    setTagInput("");
  };

  const handleTagInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addTag();
    }
  };

  const removeTag = (tagToRemove: string) => {
    setTags((existing) => existing.filter((tag) => tag !== tagToRemove));
  };

  const isSaving = createMutation.isLoading || updateMutation.isLoading;
  const isDiscarding = discardMutation.isLoading;
  const disableSave =
    !title ||
    !content ||
    tags.length === 0 ||
    isSaving ||
    isDiscarding ||
    (!isNew && detailQuery.isLoading);
  const disableSubmit = !draftVersion || submitMutation.isLoading || isDiscarding;
  const canDiscard = Boolean(activeNoteId) && (detailQuery.data?.has_draft || draftVersion);

  const parsedReviewerIds = Array.from(new Set(parseReviewerInput(reviewersText)));
  const isReviewConfirmDisabled =
    submitMutation.isLoading || !reviewTitle.trim() || parsedReviewerIds.length === 0;

  const showLoadingState = !isNew && detailQuery.isLoading && !initializedExisting;

  return (
    <Flex direction={{ base: "column", xl: "row" }} gap={8} align="flex-start">
      <Stack spacing={6} flex="1">
        
        <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <CardHeader borderBottom="1px solid" borderColor="github.border.default">
            <Flex justify="space-between" align={{ base: "flex-start", md: "center" }} direction={{ base: "column", md: "row" }} gap={2}>
              <Stack spacing={0} flex={1}>
                <Heading size="sm" fontWeight={600}>
                  {isNew ? "Compose note" : "Editing note"}: {!isNew && detailQuery.data ? detailQuery.data.id : ''}
                </Heading>
              </Stack>
              {!isNew && detailQuery.data && (
                <HStack spacing={2} align="center">
                  <Box
                    px={2}
                    py={0.5}
                    borderRadius="full"
                    bg="github.bg.secondary"
                    border="1px solid"
                    borderColor="github.border.default"
                    fontSize="xs"
                    fontWeight={600}
                  >
                    v{detailQuery.data.version_index}
                  </Box>
                  <Text fontSize="xs" color="github.fg.muted" textTransform="uppercase" letterSpacing="wider">
                    {detailQuery.data.state}
                  </Text>
                </HStack>
              )}
            </Flex>
          </CardHeader>
          <CardBody>
            {showLoadingState ? (
              <Flex justify="center" py={12}>
                <Spinner thickness="3px" color="github.fg.muted" />
              </Flex>
            ) : (
              <Stack spacing={4}>
                {showChangesRequestedAlert && (
                  <Alert status="warning" variant="left-accent" alignItems="flex-start" borderRadius="md">
                    <AlertIcon />
                    <Stack spacing={1} flex={1} minW={0}>
                      <AlertTitle fontSize="sm">Your reviewers asked for updates</AlertTitle>
                      <AlertDescription fontSize="sm" color="orange.900">
                        Continue editing below and submit again when ready—this will reopen the existing review so the conversation stays in one place.
                      </AlertDescription>
                      {activeReviewId && (
                        <Button
                          size="xs"
                          variant="link"
                          colorScheme="orange"
                          alignSelf="flex-start"
                          onClick={() => navigate(`/review/${activeReviewId}`)}
                        >
                          View review details
                        </Button>
                      )}
                    </Stack>
                  </Alert>
                )}
                <FormControl>
                  <FormLabel fontWeight={600} fontSize="sm" mb={1}>
                    Title
                  </FormLabel>
                  <Input
                    value={title}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setTitle(event.target.value)}
                    placeholder="Enter a concise title"
                    size="sm"
                    bg="github.bg.primary"
                    borderColor="github.border.default"
                    _hover={{ borderColor: "github.border.emphasis" }}
                    _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                  />
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight={600} fontSize="sm" mb={1}>
                    Tags
                  </FormLabel>
                  <Stack spacing={2}>
                    <Input
                      value={tagInput}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => setTagInput(event.target.value)}
                      onKeyDown={handleTagInputKeyDown}
                      onBlur={addTag}
                      placeholder="Add a tag and press Enter"
                      size="sm"
                      bg="github.bg.primary"
                      borderColor="github.border.default"
                      _hover={{ borderColor: "github.border.emphasis" }}
                      _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                    />
                    {tags.length > 0 && (
                      <Flex gap={2} flexWrap="wrap">
                        {tags.map((tag) => (
                          <HStack
                            key={tag}
                            spacing={1}
                            px={2}
                            py={0.5}
                            borderRadius="full"
                            bg="github.bg.secondary"
                            border="1px solid"
                            borderColor="github.border.default"
                            cursor="pointer"
                            title="Double-click to search by this tag"
                            onDoubleClick={() => goToTag(tag)}
                          >
                            <Text fontSize="xs" textTransform="lowercase">
                              {tag}
                            </Text>
                            <CloseButton
                              size="2xs"
                              p={0}
                              minW="auto"
                              onClick={() => removeTag(tag)}
                              onDoubleClick={(event: ReactMouseEvent<HTMLButtonElement>) => event.stopPropagation()}
                              color="github.fg.muted"
                              _hover={{ background: "transparent", color: "github.fg.default" }}
                              aria-label={`Remove tag ${tag}`}
                              style={{ fontSize: "10px" }}
                            />
                          </HStack>
                        ))}
                      </Flex>
                    )}
                  </Stack>
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight={600} fontSize="sm" mb={1}>
                    Content
                  </FormLabel>
                  <Box
                    data-color-mode="light"
                    borderRadius="md"
                    border="1px solid"
                    borderColor="github.border.default"
                    overflow="hidden"
                  >
                    <MDEditor value={content} onChange={setContent} height={420} />
                  </Box>
                </FormControl>
                {draftVersion && (
                  <Box
                    border="1px solid"
                    borderColor="github.success.emphasis"
                    bg="github.success.subtle"
                    borderRadius="md"
                    p={3}
                  >
                    <Text fontSize="xs" color="github.success.fg">
                      Draft saved as version {draftVersion.version_index} for note {draftVersion.id}
                    </Text>
                  </Box>
                )}
              </Stack>
            )}
          </CardBody>
          <CardFooter borderTop="1px solid" borderColor="github.border.default">
            <HStack spacing={3} width="full" flexWrap={{ base: "wrap", md: "nowrap" }}>
              <Button
                variant="primary"
                size="sm"
                onClick={handleSave}
                isDisabled={disableSave}
                isLoading={isSaving}
                flex={1}
              >
                Save draft
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleSubmit}
                isDisabled={disableSubmit}
                isLoading={submitMutation.isLoading}
                flex={1}
              >
                Submit for review
              </Button>
              {canDiscard && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={onDiscardOpen}
                  isDisabled={discardMutation.isLoading}
                  isLoading={discardMutation.isLoading}
                  flex={1}
                  color="github.danger.fg"
                  borderColor="github.border.default"
                  _hover={{ bg: "github.bg.secondary", borderColor: "github.border.emphasis" }}
                >
                  Discard draft
                </Button>
              )}
            </HStack>
          </CardFooter>
        </Card>
      </Stack>

        <Modal
          isOpen={isReviewOpen}
          onClose={() => {
            if (!submitMutation.isLoading) {
              onReviewClose();
            }
          }}
          isCentered
          size="lg"
          closeOnOverlayClick={!submitMutation.isLoading}
        >
          <ModalOverlay />
          <ModalContent bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
            <ModalHeader borderBottom="1px solid" borderColor="github.border.default">
              Submit for review
            </ModalHeader>
            <ModalBody>
              <Stack spacing={4} fontSize="sm">
                <Text color="github.fg.muted">
                  Share a quick summary and pick reviewers. We'll notify them and keep track of their decisions just like a pull request.
                </Text>
                <FormControl isRequired>
                  <FormLabel fontWeight={600}>Review title</FormLabel>
                  <Input
                    value={reviewTitle}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setReviewTitle(event.target.value)}
                    placeholder={'Something descriptive like "Enable autosave for drafts"'}
                    size="sm"
                    bg="github.bg.primary"
                    borderColor="github.border.default"
                    _hover={{ borderColor: "github.border.emphasis" }}
                    _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                  />
                </FormControl>
                <FormControl>
                  <FormLabel fontWeight={600}>Summary</FormLabel>
                  <Textarea
                    value={reviewSummary}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setReviewSummary(event.target.value)}
                    placeholder="Help reviewers understand why this change matters."
                    size="sm"
                    rows={4}
                    bg="github.bg.primary"
                    borderColor="github.border.default"
                    _hover={{ borderColor: "github.border.emphasis" }}
                    _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                  />
                </FormControl>
                <FormControl isRequired>
                  <FormLabel fontWeight={600}>Reviewers</FormLabel>
                  <Textarea
                    value={reviewersText}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setReviewersText(event.target.value)}
                    placeholder="Add usernames separated by commas or spaces"
                    size="sm"
                    rows={2}
                    bg="github.bg.primary"
                    borderColor="github.border.default"
                    _hover={{ borderColor: "github.border.emphasis" }}
                    _focus={{ borderColor: "github.border.emphasis", boxShadow: "0 0 0 1px rgba(209, 217, 224, 0.8)" }}
                  />
                  <FormHelperText color="github.fg.muted">
                    {parsedReviewerIds.length > 0
                      ? `We'll request a review from ${parsedReviewerIds.join(", ")}.`
                      : "Enter at least one reviewer ID."}
                  </FormHelperText>
                </FormControl>
              </Stack>
            </ModalBody>
            <ModalFooter borderTop="1px solid" borderColor="github.border.default" gap={3}>
              <Button
                variant="secondary"
                size="sm"
                onClick={onReviewClose}
                isDisabled={submitMutation.isLoading}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleConfirmReview}
                isDisabled={isReviewConfirmDisabled}
                isLoading={submitMutation.isLoading}
              >
                Send review request
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>

      <Modal isOpen={isDiscardOpen} onClose={onDiscardClose} isCentered>
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Discard Draft?</ModalHeader>
          <ModalBody>
            <Text>Are you sure you want to discard this draft? This action cannot be undone.</Text>
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" size="sm" mr={3} onClick={onDiscardClose}>
              Cancel
            </Button>
            <Button
              colorScheme="red"
              size="sm"
              onClick={() => {
                onDiscardClose();
                discardMutation.mutate();
              }}
              isLoading={discardMutation.isLoading}
            >
              Discard
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <Box width={{ base: "100%", xl: "320px" }}>
        <Stack spacing={4} position="sticky" top={0}>
          <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
            <CardHeader borderBottom="1px solid" borderColor="github.border.default">
              <Heading size="sm" fontWeight={600}>
                My drafts
              </Heading>
            </CardHeader>
            <CardBody>
              {draftsQuery.isLoading ? (
                <Flex justify="center" py={6}>
                  <Spinner thickness="3px" color="github.fg.muted" />
                </Flex>
              ) : draftsQuery.data && draftsQuery.data.length > 0 ? (
                <Stack spacing={3}>
                  {draftsQuery.data.map((draft: NoteResponse) => {
                    const isActive = !isNew && activeNoteId === draft.id;
                    return (
                      <Box
                        key={draft.version_id}
                        onClick={() => loadDraft(draft)}
                        border="1px solid"
                        borderColor={isActive ? "github.border.emphasis" : "github.border.default"}
                        bg={isActive ? "github.bg.secondary" : "github.bg.primary"}
                        borderRadius="md"
                        px={3}
                        py={3}
                        cursor="pointer"
                        transition="all 0.15s ease"
                        _hover={{ borderColor: "github.border.emphasis", bg: "github.bg.secondary" }}
                      >
                        <Flex align="center" justify="space-between" gap={3}>
                          <Stack spacing={1} flex="1" minW={0}>
                            <Text fontWeight={600} fontSize="sm" noOfLines={1}>
                              {draft.title}
                            </Text>
                            <Text fontSize="xs" color="github.fg.muted">
                              Created {dayjs(draft.created_at).format("MMM D, YYYY h:mm A")}
                            </Text>
                            {draft.tags.length > 0 && (
                              <Flex gap={2} flexWrap="wrap">
                                {draft.tags.map((tag: string) => (
                                  <Box
                                    key={tag}
                                    px={2}
                                    py={0.5}
                                    borderRadius="full"
                                    bg="github.bg.secondary"
                                    border="1px solid"
                                    borderColor="github.border.default"
                                    cursor="pointer"
                                    title="Double-click to search by this tag"
                                    onDoubleClick={() => goToTag(tag)}
                                  >
                                    <Text fontSize="xs" textTransform="lowercase">
                                      {tag.toLowerCase()}
                                    </Text>
                                  </Box>
                                ))}
                              </Flex>
                            )}
                          </Stack>
                          <Icon as={EditIcon} boxSize={4} color="github.fg.muted" flexShrink={0} />
                        </Flex>
                      </Box>
                    );
                  })}
                </Stack>
              ) : (
                <Text fontSize="sm" color="github.fg.muted">
                  Drafts you save will appear here for quick access.
                </Text>
              )}
            </CardBody>
            <CardFooter borderTop="1px solid" borderColor="github.border.default">
              <Button onClick={() => navigate("/edit/new")} size="sm" variant="secondary" width="full">
                Start new note
              </Button>
            </CardFooter>
          </Card>
        </Stack>
      </Box>
    </Flex>
  );
}
