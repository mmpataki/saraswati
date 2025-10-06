import { Badge, Box, Heading, Stack, Text } from "@chakra-ui/react";
import MDEditor from "@uiw/react-md-editor";
import dayjs from "dayjs";

import { useSearchNavigation } from "../hooks/useSearchNavigation";

export type NotePreviewProps = {
  title: string;
  content: string;
  tags: string[];
  createdAt?: string;
  createdBy?: string;
};

export function NotePreview({ title, content, tags, createdAt, createdBy }: NotePreviewProps): JSX.Element {
  const { goToTag } = useSearchNavigation();

  return (
    <Stack spacing={4} p={6} borderRadius="xl" shadow="md" bg="white" _dark={{ bg: "gray.700" }}>
      <Heading size="md">{title}</Heading>
      <Stack direction="row" spacing={2} flexWrap="wrap">
        {tags.map((tag) => (
          <Badge
            key={tag}
            variant="subtle"
            cursor="pointer"
            title="Double-click to search by this tag"
            onDoubleClick={() => goToTag(tag)}
          >
            {tag}
          </Badge>
        ))}
      </Stack>
      <Box data-color-mode="light">
        <MDEditor.Markdown source={content} />
      </Box>
      <Text fontSize="sm" color="gray.500">
        {createdBy ? `Authored by ${createdBy}` : ""}
        {createdAt ? ` • ${dayjs(createdAt).format("MMM D, YYYY h:mm A")}` : ""}
      </Text>
    </Stack>
  );
}
