import { Box, Heading } from "@chakra-ui/react";
import DiffViewer from "react-diff-viewer-continued";

export type VersionDiffProps = {
  oldContent: string;
  newContent: string;
  title?: string;
};

export function VersionDiff({ oldContent, newContent, title }: VersionDiffProps): JSX.Element {
  return (
    <Box fontSize="0.85rem" sx={{
      // Target the diff viewer container and monospace the code area
      ".react-diff-viewer": {
        fontSize: "0.85rem",
      },
      ".react-diff-viewer .diff-line": {
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, "Roboto Mono", "Courier New", monospace'
      }
    }}>
      {title && (
        <Heading size="md" mb={4}>
          {title}
        </Heading>
      )}
      <DiffViewer
        oldValue={oldContent}
        newValue={newContent}
        splitView
        disableWordDiff
        leftTitle="Previous"
        rightTitle="Draft"
      />
    </Box>
  );
}
