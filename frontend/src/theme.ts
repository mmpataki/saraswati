import { extendTheme, type ThemeConfig } from "@chakra-ui/react";

const config: ThemeConfig = {
  initialColorMode: "light",
  useSystemColorMode: false,
};

// GitHub-inspired color palette
const colors = {
  github: {
    bg: {
      primary: "#ffffff",
      secondary: "#f6f8fa",
      tertiary: "#0d1117",
      canvas: "#ffffff",
      overlay: "#ffffff",
      inset: "#f6f8fa",
    },
    border: {
      default: "#d0d7de",
      muted: "#d8dee4",
      subtle: "#eaeef2",
    },
    fg: {
      default: "#1f2328",
      muted: "#656d76",
      subtle: "#6e7781",
      onEmphasis: "#ffffff",
    },
    accent: {
      fg: "#0969da",
      emphasis: "#0969da",
      muted: "#54aeff",
      subtle: "#ddf4ff",
    },
    success: {
      fg: "#1a7f37",
      emphasis: "#2da44e",
      muted: "#4ac26b",
      subtle: "#dafbe1",
    },
    attention: {
      fg: "#9a6700",
      emphasis: "#bf8700",
      muted: "#d4a72c",
      subtle: "#fff8c5",
    },
    danger: {
      fg: "#d1242f",
      emphasis: "#cf222e",
      muted: "#ff8182",
      subtle: "#ffebe9",
    },
    dark: {
      bg: "#0d1117",
      bgSecondary: "#161b22",
      border: "#30363d",
      fg: "#c9d1d9",
    },
  },
};

const fonts = {
  heading: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif`,
  body: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif`,
  mono: `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`,
};

const styles = {
  global: {
    body: {
      bg: "github.bg.secondary",
      color: "github.fg.default",
    },
  },
};

const components = {
  Button: {
    baseStyle: {
      fontWeight: 500,
      borderRadius: "6px",
    },
    variants: {
      primary: {
        bg: "github.success.emphasis",
        color: "white",
        _hover: {
          bg: "github.success.fg",
        },
      },
      secondary: {
        bg: "github.bg.inset",
        color: "github.fg.default",
        border: "1px solid",
        borderColor: "github.border.default",
        _hover: {
          bg: "github.bg.secondary",
          borderColor: "github.border.muted",
        },
      },
      danger: {
        bg: "github.danger.emphasis",
        color: "white",
        _hover: {
          bg: "github.danger.fg",
        },
      },
    },
    defaultProps: {
      variant: "secondary",
    },
  },
  Input: {
    variants: {
      outline: {
        field: {
          borderColor: "github.border.default",
          bg: "github.bg.canvas",
          _hover: {
            borderColor: "github.border.muted",
          },
          _focus: {
            borderColor: "github.accent.emphasis",
            boxShadow: "0 0 0 3px rgba(9, 105, 218, 0.3)",
          },
        },
      },
    },
  },
  Textarea: {
    variants: {
      outline: {
        borderColor: "github.border.default",
        bg: "github.bg.canvas",
        _hover: {
          borderColor: "github.border.muted",
        },
        _focus: {
          borderColor: "github.accent.emphasis",
          boxShadow: "0 0 0 3px rgba(9, 105, 218, 0.3)",
        },
      },
    },
  },
  Card: {
    baseStyle: {
      container: {
        bg: "github.bg.canvas",
        border: "1px solid",
        borderColor: "github.border.default",
        borderRadius: "6px",
        boxShadow: "none",
      },
    },
  },
  Badge: {
    baseStyle: {
      borderRadius: "12px",
      px: 2,
      fontWeight: 500,
      fontSize: "xs",
    },
    variants: {
      subtle: {
        bg: "github.accent.subtle",
        color: "github.accent.fg",
      },
    },
  },
  Heading: {
    baseStyle: {
      fontWeight: 600,
    },
  },
};

const theme = extendTheme({
  config,
  colors,
  fonts,
  styles,
  components,
});

export default theme;
