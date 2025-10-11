import { ChevronDownIcon } from "@chakra-ui/icons";
import {
  Box,
  Button,
  Flex,
  HStack,
  Input,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Spinner,
  Text,
} from "@chakra-ui/react";
import { ReactElement, cloneElement } from "react";

export type FacetDropdownProps = {
  label: string;
  value: string;
  options: string[];
  searchValue: string;
  onSearchChange: (next: string) => void;
  onSelect: (next: string) => void;
  onClear: () => void;
  icon?: ReactElement;
  isLoading?: boolean;
  emptyMessage?: string;
  clearLabel?: string;
};

export function FacetDropdown({
  label,
  value,
  options,
  searchValue,
  onSearchChange,
  onSelect,
  onClear,
  icon,
  isLoading = false,
  emptyMessage,
  clearLabel,
}: FacetDropdownProps): JSX.Element {
  const filteredOptions = options.filter((option) =>
    option.toLowerCase().includes(searchValue.toLowerCase())
  );

  const resolvedEmptyMessage = emptyMessage ?? `No ${label.toLowerCase()} found`;
  const resolvedClearLabel = clearLabel ?? `Clear ${label.toLowerCase()} filter`;
  const renderIcon = (key: string) => (icon ? cloneElement(icon, { key }) : null);

  return (
    <Menu closeOnSelect={false} autoSelect={false}>
      {({ onClose }) => (
        <>
          <MenuButton
            as={Button}
            rightIcon={<ChevronDownIcon />}
            size="xs"
            variant="outline"
            borderColor="gray.200"
            _hover={{ bg: "gray.50", borderColor: "gray.300" }}
            _active={{ bg: "gray.100" }}
            fontWeight={value ? 500 : 400}
            color={value ? "blue.600" : "gray.600"}
          >
            <HStack spacing={1}>
              {icon ? renderIcon("button-icon") : null}
              <Text>{value || label}</Text>
            </HStack>
          </MenuButton>
          <MenuList maxH="300px" overflowY="auto" shadow="lg">
            <Box px={3} py={2}>
              <Input
                placeholder={`Search ${label.toLowerCase()}...`}
                size="xs"
                value={searchValue}
                onChange={(event) => onSearchChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    const nextValue = event.currentTarget.value.trim();
                    onSelect(nextValue);
                    onSearchChange(nextValue);
                    onClose();
                  }
                }}
                autoFocus
              />
            </Box>
            <Box h="1px" bg="gray.100" />
            {value && (
              <>
                <MenuItem
                  onClick={() => {
                    onClear();
                    onSearchChange("");
                    onClose();
                  }}
                  fontWeight={500}
                  color="red.600"
                >
                  {resolvedClearLabel}
                </MenuItem>
                <Box h="1px" bg="gray.100" my={1} />
              </>
            )}
            {isLoading ? (
              <Flex align="center" justify="center" py={4}>
                <Spinner size="sm" />
              </Flex>
            ) : filteredOptions.length === 0 ? (
              <Box px={3} py={2}>
                <Text fontSize="xs" color="gray.500">
                  {resolvedEmptyMessage}
                </Text>
              </Box>
            ) : (
              filteredOptions.map((option) => (
                <MenuItem
                  key={option}
                  onClick={() => {
                    onSelect(option);
                    onSearchChange("");
                    onClose();
                  }}
                  bg={value === option ? "blue.50" : undefined}
                  fontWeight={value === option ? 500 : 400}
                >
                  <HStack>
                    {icon ? renderIcon(`option-${option}`) : null}
                    <Text>{option}</Text>
                  </HStack>
                </MenuItem>
              ))
            )}
          </MenuList>
        </>
      )}
    </Menu>
  );
}
