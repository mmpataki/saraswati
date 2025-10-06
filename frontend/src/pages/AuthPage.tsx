import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import {
  Box,
  Button,
  Container,
  FormControl,
  FormLabel,
  Heading,
  Input,
  Stack,
  Text,
  Image,
  useToast
} from "@chakra-ui/react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { api } from "../api/client";

export function AuthPage(): JSX.Element {
  const { login, loading, token, canRegister } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [regMode, setRegMode] = useState(false);
  const [regName, setRegName] = useState("");
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    if (token) {
      navigate("/search", { replace: true });
    }
  }, [token, navigate]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await login(username, password);
      toast({ title: "Welcome back!", status: "success", duration: 3000, isClosable: true });
      navigate("/search");
    } catch (error) {
      console.error(error);
      toast({ title: "Login failed", status: "error", duration: 3000, isClosable: true });
    }
  };

  const handleRegister = async () => {
    try {
      const resp = await api.post("/auth/register", { username, password, name: regName });
      toast({ title: "Registered", status: "success", duration: 3000, isClosable: true });
      setRegMode(false);
      setPassword("");
      setRegName("");
    } catch (err) {
      console.error(err);
      toast({ title: "Registration failed", status: "error", duration: 3000, isClosable: true });
    }
  };

  return (
    <Box minH="100vh" bg="github.bg.secondary" display="flex" alignItems="center" justifyContent="center">
      <Container maxW="420px">
        <Stack spacing={6} align="center">
          <Box textAlign="center">

          </Box>
          
          {!regMode ? (
            <Box
              as="form"
              w="full"
              p={6}
              bg="github.bg.primary"
              border="1px solid"
              borderColor="github.border.default"
              borderRadius="md"
              onSubmit={handleSubmit}
            >
              <Stack spacing={4}>
                <Image src="assets/saraswati.png" alt="Saraswati" boxSize="100px" objectFit="contain" mx="auto" mb={2} />
                <Heading size="md" textAlign="center" fontWeight={400} mb={2}>
                  Sign in to Saraswati
                </Heading>
                <Text fontSize="xs" textAlign="center" color="github.fg.muted">Knowledge management & review for AIs</Text>
                <FormControl>
                  <FormLabel fontSize="sm" fontWeight={600} mb={1}>Username</FormLabel>
                  <Input
                    value={username}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setUsername(event.target.value)}
                    required
                    bg="github.bg.primary"
                    borderColor="github.border.default"
                    _hover={{ borderColor: "github.border.emphasis" }}
                    _focus={{
                      borderColor: "github.accent.emphasis",
                      boxShadow: "0 0 0 3px rgba(9, 105, 218, 0.3)",
                    }}
                  />
                </FormControl>

                <FormControl>
                  <FormLabel fontSize="sm" fontWeight={600} mb={1}>Password</FormLabel>
                  <Input
                    type="password"
                    value={password}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)}
                    required
                    bg="github.bg.primary"
                    borderColor="github.border.default"
                    _hover={{ borderColor: "github.border.emphasis" }}
                    _focus={{
                      borderColor: "github.accent.emphasis",
                      boxShadow: "0 0 0 3px rgba(9, 105, 218, 0.3)",
                    }}
                  />
                </FormControl>

                <Button
                  type="submit"
                  variant="primary"
                  isLoading={loading}
                  size="lg"
                  w="full"
                  mt={2}
                >
                  Sign in
                </Button>

                {canRegister && (
                  <Text
                    fontSize="sm"
                    color="github.accent.emphasis"
                    textAlign="center"
                    mt={2}
                    cursor="pointer"
                    onClick={() => setRegMode(true)}
                  >
                    Create an account
                  </Text>
                )}

                {!canRegister && (
                  <Text fontSize="xs" color="github.fg.muted" textAlign="center" pt={2}>
                    Use your organization credentials to access the knowledge base and review queue.
                  </Text>
                )}
              </Stack>
            </Box>
          ) : (
            <Box
              w="full"
              p={6}
              bg="github.bg.primary"
              border="1px solid"
              borderColor="github.border.default"
              borderRadius="md"
            >
              <Stack spacing={4}>
                <Heading size="md" textAlign="center" fontWeight={400} mb={2}>
                  Create an account
                </Heading>

                <FormControl>
                  <FormLabel fontSize="sm" fontWeight={600} mb={1}>Username</FormLabel>
                  <Input value={username} onChange={(e) => setUsername(e.target.value)} required />
                </FormControl>

                <FormControl>
                  <FormLabel fontSize="sm" fontWeight={600} mb={1}>Full name</FormLabel>
                  <Input value={regName} onChange={(e) => setRegName(e.target.value)} />
                </FormControl>

                <FormControl>
                  <FormLabel fontSize="sm" fontWeight={600} mb={1}>Password</FormLabel>
                  <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </FormControl>

                <Button variant="primary" size="lg" w="full" onClick={handleRegister}>
                  Register
                </Button>

                <Button variant="link" size="sm" onClick={() => setRegMode(false)}>
                  Back to sign in
                </Button>
              </Stack>
            </Box>
          )}
        </Stack>
      </Container>
    </Box>
  );
}
