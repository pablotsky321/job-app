import * as React from "react";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   Select — minimal accessible select using project tokens.
   Themed with project palette only (primary, gray, semantic).
   ────────────────────────────────────────────────────────────── */

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  placeholder?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, placeholder, ...props }, ref) => {
    return (
      <select
        ref={ref}
        className={cn(
          "flex h-10 w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm",
          "text-gray-900 ring-offset-white",
          "focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {children}
      </select>
    );
  },
);
Select.displayName = "Select";

export interface SelectOptionProps
  extends React.OptionHTMLAttributes<HTMLOptionElement> {}

export const SelectOption = React.forwardRef<
  HTMLOptionElement,
  SelectOptionProps
>(({ className, ...props }, ref) => {
  return (
    <option
      ref={ref}
      className={cn("text-gray-900", className)}
      {...props}
    />
  );
});
SelectOption.displayName = "SelectOption";
