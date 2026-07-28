import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/* ──────────────────────────────────────────────────────────────
   PlainText — wrapper that renders children as plain React text.
   Always renders safely via React children (no raw HTML injection).
   Ensures every screen rendering vacancy descriptions, score
   summaries, or entries uses it consistently.
   ────────────────────────────────────────────────────────────── */

export interface PlainTextProps {
  children: ReactNode;
  className?: string;
  as?: "p" | "span" | "div";
}

export function PlainText({ children, className, as: Tag = "span" }: PlainTextProps) {
  return <Tag className={cn("whitespace-pre-wrap", className)}>{children}</Tag>;
}
