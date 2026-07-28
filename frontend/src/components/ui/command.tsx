import * as React from "react";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   Command / Combobox — minimal accessible command palette.
   Used in Onboarding Step 3 (companies) and Sources view.
   Themed with project palette only (primary, gray, semantic).
   ────────────────────────────────────────────────────────────── */

export interface CommandProps {
  children: React.ReactNode;
  className?: string;
}

export function Command({ children, className }: CommandProps) {
  return (
    <div
      className={cn(
        "flex h-full w-full flex-col overflow-hidden rounded-md bg-white text-gray-900",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface CommandInputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

export const CommandInput = React.forwardRef<HTMLInputElement, CommandInputProps>(
  ({ className, ...props }, ref) => {
    return (
      <div className="flex items-center border-b border-gray-200 px-3">
        <svg
          className="mr-2 h-4 w-4 shrink-0 text-gray-400"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          ref={ref}
          type="text"
          className={cn(
            "flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-none",
            "placeholder:text-gray-400 disabled:cursor-not-allowed disabled:opacity-50",
            className,
          )}
          {...props}
        />
      </div>
    );
  },
);
CommandInput.displayName = "CommandInput";

export interface CommandListProps {
  children: React.ReactNode;
  className?: string;
}

export function CommandList({ children, className }: CommandListProps) {
  return (
    <div
      role="listbox"
      className={cn("max-h-[300px] overflow-y-auto overflow-x-hidden", className)}
    >
      {children}
    </div>
  );
}

export interface CommandEmptyProps {
  children?: React.ReactNode;
  className?: string;
}

export function CommandEmpty({ children, className }: CommandEmptyProps) {
  return (
    <p className={cn("py-6 text-center text-sm text-gray-500", className)}>
      {children ?? "No se encontraron resultados."}
    </p>
  );
}

export interface CommandGroupProps {
  heading?: string;
  children: React.ReactNode;
  className?: string;
}

export function CommandGroup({ heading, children, className }: CommandGroupProps) {
  return (
    <div
      role="group"
      aria-label={heading}
      className={cn("overflow-hidden p-1 text-gray-900", className)}
    >
      {heading && (
        <p className="px-2 py-1.5 text-xs font-medium text-gray-500">
          {heading}
        </p>
      )}
      {children}
    </div>
  );
}

export interface CommandItemProps
  extends React.HTMLAttributes<HTMLDivElement> {
  disabled?: boolean;
  selected?: boolean;
  onSelect?: () => void;
}

export const CommandItem = React.forwardRef<HTMLDivElement, CommandItemProps>(
  ({ className, disabled, selected, onSelect, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="option"
        aria-selected={selected}
        aria-disabled={disabled}
        onClick={() => {
          if (!disabled) onSelect?.();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!disabled) onSelect?.();
          }
        }}
        tabIndex={disabled ? -1 : 0}
        className={cn(
          "relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none",
          "hover:bg-primary-50 hover:text-primary-900",
          "focus-visible:bg-primary-50 focus-visible:text-primary-900",
          selected && "bg-primary-50 text-primary-900",
          disabled && "pointer-events-none opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
CommandItem.displayName = "CommandItem";

export interface CommandSeparatorProps {
  className?: string;
}

export function CommandSeparator({ className }: CommandSeparatorProps) {
  return <div className={cn("-mx-1 h-px bg-gray-200", className)} />;
}
