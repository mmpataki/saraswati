import { Box, Button, Heading, Image, SimpleGrid, Stack, Text } from "@chakra-ui/react";
import { Link } from "react-router-dom";

export function HomePage(): JSX.Element {
  return (
    <Stack spacing={6}>
      <Box bg="github.bg.primary" p={6} borderRadius="md">
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4} alignItems="center">
          <Box>
            <Heading size="lg">Welcome to Saraswati</Heading>
            <Text mt={2} color="github.fg.muted">Your knowledge workspace.</Text>
            <Button as={Link} to="/edit/new" mt={4} colorScheme="blue" size="sm">Create note</Button>
          </Box>
          <Box textAlign="center">
            <Image src="/saraswati.png" alt="Saraswati" maxW="220px" mx="auto" borderRadius="md" />
          </Box>
        </SimpleGrid>
      </Box>

      <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
        <Box p={4} bg="github.bg.primary" borderRadius="md">
          <Heading size="sm">Quick links</Heading>
          <Stack mt={2} spacing={2}>
            <Button as={Link} to="/search" variant="ghost" size="sm">Search notes</Button>
            <Button as={Link} to="/review" variant="ghost" size="sm">Review queue</Button>
          </Stack>
        </Box>

        <Box p={4} bg="github.bg.primary" borderRadius="md">
          <Heading size="sm">Recent activity</Heading>
          <Text mt={2} color="github.fg.muted">No recent activity to display.</Text>
        </Box>
      </SimpleGrid>
    </Stack>
  );
}
