import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { authApi } from "../api/client";

type User = {
  id: string;
  name?: string;
  roles?: string[];
};

type AuthContextValue = {
  token: string | null;
  user: User | null;
  loading: boolean;
  canRegister: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const TOKEN_KEY = "saraswati_token";

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(false);
  const [canRegister, setCanRegister] = useState(false);

  useEffect(() => {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      try {
        const [, payload] = token.split(".");
        if (payload) {
          const decoded = JSON.parse(atob(payload));
          console.log('hahaha', decoded);
          setUser({
            id: decoded.sub ?? decoded.id ?? decoded.u ?? decoded.user_id ?? (decoded.email as string) ?? "user",
            name: decoded.u ?? decoded.name ?? decoded.preferred_username ?? decoded.username ?? decoded.sub,
            roles: decoded.roles ?? decoded.scope?.split(" ")
          });
        }
      } catch (error) {
        console.warn("Unable to parse JWT", error);
      }
    } else {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    }
  }, [token]);

  useEffect(() => {
    // Fetch auth capabilities (e.g., whether registration is allowed)
    let mounted = true;
    (async () => {
      try {
        const resp = await authApi.get("/capabilities");
        // Debug: log response shape when things are unexpected
        // eslint-disable-next-line no-console
        console.debug("auth capabilities response:", resp.status, resp.data);
        if (mounted) {
          // accept multiple possible keys for robustness
          const data = resp.data || {};
          const can = data.can_register ?? data.canRegister ?? false;
          setCanRegister(Boolean(can));
        }
      } catch (err) {
        // Non-fatal; default to no registration
        if (mounted) setCanRegister(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const login = async (username: string, password: string) => {
    setLoading(true);
    try {
      const response = await authApi.post("/login", { username, password });
      const { access_token: accessToken, user: profile } = response.data;
      setToken(accessToken);
      setUser({ id: profile?.id ?? username, name: profile?.name ?? username, roles: profile?.roles ?? [] });
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
  };

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      canRegister,
      login,
      logout
    }),
    [token, user, loading, canRegister]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // Defensive fallback: during some build/runtime scenarios a component may import
    // useAuth before the provider is mounted (especially with mixed JS/TS builds).
    // Instead of throwing and crashing the whole app, return a safe stub and warn.
    // This keeps pages usable while preserving developer visibility of the issue.
    // NOTE: Prefer fixing provider ordering; this is a defensive measure.
    // eslint-disable-next-line no-console
    console.warn("useAuth called outside AuthProvider - returning fallback stub");
    return {
      token: null,
      user: null,
      loading: false,
      canRegister: false,
      login: async () => {
        // no-op
      },
      logout: () => {
        // no-op
      },
    } as AuthContextValue;
  }
  return ctx;
}
