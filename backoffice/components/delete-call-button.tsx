"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { callsApi, type CallAttempt } from "@/lib/api";

type Props = {
  call: CallAttempt;
};

export function DeleteCallButton({ call }: Props) {
  const queryClient = useQueryClient();
  const router = useRouter();

  const remove = useMutation({
    mutationFn: () => callsApi.remove(call.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["calls"] });
      router.push("/calls");
    },
  });

  return (
    <div className="mt-4 flex items-center gap-2">
      <Button
        variant="outline"
        disabled={remove.isPending}
        onClick={() => {
          if (
            confirm(
              `Delete call #${call.id}? It will be hidden from the backoffice; the underlying record stays in DB.`
            )
          ) {
            remove.mutate();
          }
        }}
      >
        {remove.isPending ? "Deleting…" : "Delete"}
      </Button>
      {remove.error && (
        <p className="text-sm text-destructive">
          {(remove.error as Error).message}
        </p>
      )}
    </div>
  );
}
