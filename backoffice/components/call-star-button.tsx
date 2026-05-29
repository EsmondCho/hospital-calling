"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { callsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  id: number;
  isStarred: boolean;
  /** Query keys to invalidate after a successful toggle. */
  invalidate?: unknown[][];
};

// Star toggle for a call attempt. Filled gold when starred, outline otherwise.
// Stops click propagation so it can sit inside a clickable table row without
// navigating.
export function CallStarButton({ id, isStarred, invalidate = [] }: Props) {
  const queryClient = useQueryClient();

  const toggle = useMutation({
    mutationFn: () => callsApi.setStar(id, !isStarred),
    onSuccess: () => {
      for (const key of invalidate) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  return (
    <Button
      variant="ghost"
      size="icon"
      type="button"
      aria-label={isStarred ? "Unstar call" : "Star call"}
      aria-pressed={isStarred}
      disabled={toggle.isPending}
      onClick={(e) => {
        e.stopPropagation();
        toggle.mutate();
      }}
    >
      <Star
        className={cn(
          "size-4",
          isStarred ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"
        )}
      />
    </Button>
  );
}
