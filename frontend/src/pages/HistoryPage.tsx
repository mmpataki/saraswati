import { ChangeEvent, useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Flex,
  Heading,
  HStack,
  SimpleGrid,
  Spinner,
  Stack,
  Text,
  Select
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import dayjs from "dayjs";

import { api } from "../api/client";
import { VersionDiff } from "../components/VersionDiff";
import { NoteResponse } from "../types";

const formatTags = (tags: string[]): string[] => tags.map((tag) => tag.toLowerCase());

const buildDiffSource = (note?: Pick<NoteResponse, "title" | "tags" | "content">): string => {
  if (!note) {
    return "";
  }
  const tags = formatTags(note.tags).join(", ");
  return `Title: ${note.title || ""}\nTags: ${tags}\n\n${note.content || ""}`;
};

export function HistoryPage(): JSX.Element {
  const { noteId = "" } = useParams<{ noteId: string }>();
  const navigate = useNavigate();
  
  const [selectedVersionA, setSelectedVersionA] = useState<string>("");
  const [selectedVersionB, setSelectedVersionB] = useState<string>("");

  const historyQuery = useQuery(["note-history", noteId], async () => {
    const { data } = await api.get<NoteResponse[]>(`/notes/${noteId}/history`);
    return data;
  }, {
    enabled: Boolean(noteId)
  });

  const noteQuery = useQuery<NoteResponse>(
    ["note-detail", noteId],
    async () => {
      const { data } = await api.get<NoteResponse>(`/notes/${noteId}`);
      return data;
    },
    {
      enabled: Boolean(noteId)
    }
  );

  const versions = historyQuery.data || [];
  const sortedVersions = useMemo(() => {
    return [...versions].sort((a, b) => b.version_index - a.version_index);
  }, [versions]);

  const versionA = useMemo(() => {
    return versions.find((v: NoteResponse) => v.version_id === selectedVersionA);
  }, [versions, selectedVersionA]);

  const versionB = useMemo(() => {
    return versions.find((v: NoteResponse) => v.version_id === selectedVersionB);
  }, [versions, selectedVersionB]);

  const diffOld = buildDiffSource(versionA);
  const diffNew = buildDiffSource(versionB);

  if (historyQuery.isLoading || noteQuery.isLoading) {
    return (
      <Flex justify="center" align="center" minH="50vh">
        <Spinner thickness="3px" color="github.fg.muted" />
      </Flex>
    );
  }

  if (!noteQuery.data) {
    return (
      <Stack spacing={4}>
        <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <CardBody>
            <Heading size="sm" mb={2}>Note not found</Heading>
            <Text fontSize="sm" color="github.fg.muted">
              This note isn't available anymore.
            </Text>
          </CardBody>
        </Card>
      </Stack>
    );
  }

  return (
    <Stack spacing={4}>
      <Flex justify="flex-end">
        <Text fontSize="sm" color="github.fg.muted">
          {versions.length} version{versions.length !== 1 ? 's' : ''}
        </Text>
      </Flex>

      <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
        <CardBody py={3}>
          <Stack spacing={2}>
            <Heading size="md" fontWeight={600}>
              {noteQuery.data.title}
            </Heading>
            <Text fontSize="sm" color="github.fg.muted">
              Version history
            </Text>
          </Stack>
        </CardBody>
      </Card>

      <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
        <CardHeader pb={2}>
          <Heading size="sm" fontWeight={600}>
            Compare versions
          </Heading>
        </CardHeader>
        <CardBody pt={2}>
          <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
            <Box>
              <Text fontSize="xs" fontWeight={600} mb={1}>From (older)</Text>
              <Select
                placeholder="Select version A"
                value={selectedVersionA}
                onChange={(e: ChangeEvent<HTMLSelectElement>) => setSelectedVersionA(e.target.value)}
                size="sm"
                bg="github.bg.primary"
                borderColor="github.border.default"
              >
                {sortedVersions.map((version) => (
                  <option key={version.version_id} value={version.version_id}>
                    v{version.version_index} - {version.state} ({dayjs(version.created_at).format("MMM D, YYYY")})
                  </option>
                ))}
              </Select>
            </Box>
            <Box>
              <Text fontSize="xs" fontWeight={600} mb={1}>To (newer)</Text>
              <Select
                placeholder="Select version B"
                value={selectedVersionB}
                onChange={(e: ChangeEvent<HTMLSelectElement>) => setSelectedVersionB(e.target.value)}
                size="sm"
                bg="github.bg.primary"
                borderColor="github.border.default"
              >
                {sortedVersions.map((version) => (
                  <option key={version.version_id} value={version.version_id}>
                    v{version.version_index} - {version.state} ({dayjs(version.created_at).format("MMM D, YYYY")})
                  </option>
                ))}
              </Select>
            </Box>
          </SimpleGrid>
        </CardBody>
      </Card>

      {selectedVersionA && selectedVersionB && (
        <Card bg="github.bg.primary" border="1px solid" borderColor="github.border.default">
          <CardHeader pb={2}>
            <Heading size="sm" fontWeight={600}>
              Comparison: v{versionA?.version_index} → v{versionB?.version_index}
            </Heading>
          </CardHeader>
          <CardBody pt={2}>
            <VersionDiff oldContent={diffOld} newContent={diffNew} />
          </CardBody>
        </Card>
      )}
    </Stack>
  );
}