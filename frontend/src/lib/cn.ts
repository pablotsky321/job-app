/**
 * Utility to merge Tailwind CSS classes with support for conditional classes.
 * Combines clsx for conditional logic and tailwind-merge for Tailwind class resolution.
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
