import { useEffect } from "react";
import { Avatar, Badge, Box, Button, Container, Flex, Heading, HStack, IconButton, Menu, MenuButton, MenuItem, MenuList, Spacer, Tooltip, Text } from "@chakra-ui/react";
import { EditIcon, QuestionOutlineIcon } from "@chakra-ui/icons";
import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";
import { ReviewSummary } from "../types";

export function AppLayout(): JSX.Element | null {
  const { token, logout, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!token) {
      navigate("/auth", { replace: true });
    }
  }, [token, navigate]);

  if (!token) {
    return null;
  }

  const isReviewActive = location.pathname.includes("review");
  const isEditActive = location.pathname.includes("edit");

  const reviewInboxQuery = useQuery<ReviewSummary[]>(
    ["reviews", "inbox-count"],
    async () => {
      const { data } = await api.get<ReviewSummary[]>("/reviews", {
        params: { mine: "true", status: "open,changes_requested" }
      });
      return data;
    },
    {
      refetchInterval: 60_000,
      staleTime: 30_000
    }
  );

  const reviewCount = reviewInboxQuery.data?.length ?? 0;

  return (
    <Flex direction="column" height="100vh" bg="github.bg.secondary">
      <Box
        as="header"
        bg="github.dark.bg"
        borderBottom="1px solid"
        borderColor="github.dark.border"
        color="github.dark.fg"
      >
        <Container maxW="container.xl">
          <Flex align="center" py={2} gap={4}>
            <Heading 
              size="sm" 
              fontWeight={700} 
              letterSpacing="wide" 
              mr={6}
              cursor="pointer"
              _hover={{ color: "white" }}
              onClick={() => navigate("/search")}
            >
              Saraswati
            </Heading>
            <Spacer />
            <HStack spacing={2}>
              <Tooltip label="Reviews" placement="bottom">
                <Box position="relative">
                  <IconButton
                    aria-label="Review queue"
                    icon={<QuestionOutlineIcon />}
                    size="sm"
                    variant={isReviewActive ? "solid" : "ghost"}
                    colorScheme="orange"
                    onClick={() => navigate("/review")}
                  />
                  {reviewCount > 0 && (
                    <Badge
                      colorScheme="red"
                      borderRadius="full"
                      position="absolute"
                      top={-1}
                      right={-1}
                      fontSize="2xs"
                      px={1}
                    >
                      {reviewCount > 99 ? "99+" : reviewCount}
                    </Badge>
                  )}
                </Box>
              </Tooltip>
              <Tooltip label="Create note" placement="bottom">
                <IconButton
                  aria-label="Create note"
                  icon={<EditIcon />}
                  size="sm"
                  variant={isEditActive ? "solid" : "ghost"}
                  colorScheme="blue"
                  onClick={() => navigate("/edit/new")}
                />
              </Tooltip>
              <Menu placement="bottom-end">
                <MenuButton
                  as={Button}
                  variant="ghost"
                  size="sm"
                  px={1}
                  py={1}
                  display="inline-flex"
                  alignItems="center"
                  justifyContent="center"
                  color="whiteAlpha.900"
                  bg="transparent"
                  minW="auto"
                  _hover={{ bg: "rgba(255,255,255,0.04)" }}
                  _focus={{ boxShadow: "none" }}
                >
                  <Tooltip label={user?.name || user?.id || "user"} placement="bottom">
                    <Avatar size="sm" name={user?.name || user?.id || "user"} bg="gray.600" color="white" />
                  </Tooltip>
                </MenuButton>
                <MenuList zIndex={50} bg="white" color="gray.800" borderColor="gray.200" boxShadow="lg" mt={2} minW="160px" borderRadius="md">
                  <MenuItem onClick={() => logout()}>
                    Sign out
                  </MenuItem>
                </MenuList>
              </Menu>
            </HStack>
          </Flex>
        </Container>
      </Box>
      <Box as="main" flex="1" overflowY="auto">
        <Container maxW="container.xl" py={6}>
          <Outlet />
        </Container>
      </Box>
    </Flex>
  );
}
