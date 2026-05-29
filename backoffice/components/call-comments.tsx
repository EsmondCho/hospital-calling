"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { callsApi, meApi, type CallComment } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type Props = {
  callId: number;
};

const TEXTAREA_CLASS =
  "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

// Operator comments on a call attempt. The add form sits ABOVE the list, the
// server returns comments newest-first (rendered as-is), and edit/delete show
// only on the viewer's own comments. Comments are unpaginated.
export function CallComments({ callId }: Props) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");

  const queryKey = ["call-comments", callId];
  const invalidate = () => queryClient.invalidateQueries({ queryKey });

  // Who's viewing — drives own-only edit/delete. Null in local dev (no auth).
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: meApi.get });

  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => callsApi.comments(callId),
  });

  const add = useMutation({
    mutationFn: (text: string) => callsApi.addComment(callId, text),
    onSuccess: () => {
      setBody("");
      invalidate();
    },
  });

  return (
    <div className="space-y-4">
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          const text = body.trim();
          if (!text) return;
          add.mutate(text);
        }}
      >
        <textarea
          className={TEXTAREA_CLASS}
          rows={3}
          placeholder="Add a comment…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="flex justify-end">
          <Button type="submit" disabled={add.isPending || !body.trim()}>
            {add.isPending ? "Adding…" : "Add comment"}
          </Button>
        </div>
        {add.error && (
          <p className="text-sm text-destructive">
            {(add.error as Error).message}
          </p>
        )}
      </form>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && (
        <p className="text-sm text-destructive">{(error as Error).message}</p>
      )}
      {data && data.length === 0 && (
        <p className="text-sm text-muted-foreground">No comments yet.</p>
      )}
      {data && data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {data.map((c) => (
            <CommentItem
              key={c.id}
              callId={callId}
              comment={c}
              isOwn={me?.user != null && c.author === me.user}
              onChanged={invalidate}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function CommentItem({
  callId,
  comment,
  isOwn,
  onChanged,
}: {
  callId: number;
  comment: CallComment;
  isOwn: boolean;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);

  const save = useMutation({
    mutationFn: (text: string) =>
      callsApi.updateComment(callId, comment.id, text),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
  });

  const remove = useMutation({
    mutationFn: () => callsApi.deleteComment(callId, comment.id),
    onSuccess: onChanged,
  });

  return (
    <li className="rounded-md border border-input px-3 py-2 text-sm">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          {editing ? (
            <textarea
              className={TEXTAREA_CLASS}
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          ) : (
            <p className="whitespace-pre-wrap break-words">{comment.body}</p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="font-medium">{comment.author}</span>
            {" · "}
            {formatDateTime(comment.created_at)}
          </p>
        </div>
        {isOwn && !editing && (
          <div className="flex shrink-0 gap-1">
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => {
                setDraft(comment.body);
                setEditing(true);
              }}
            >
              Edit
            </Button>
            <Button
              variant="ghost"
              size="sm"
              type="button"
              aria-label="Delete comment"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              ✕
            </Button>
          </div>
        )}
      </div>
      {editing && (
        <div className="mt-2 flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            type="button"
            onClick={() => setEditing(false)}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            type="button"
            disabled={save.isPending || !draft.trim()}
            onClick={() => save.mutate(draft.trim())}
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      )}
      {save.error && (
        <p className="mt-1 text-sm text-destructive">
          {(save.error as Error).message}
        </p>
      )}
      {remove.error && (
        <p className="mt-1 text-sm text-destructive">
          {(remove.error as Error).message}
        </p>
      )}
    </li>
  );
}
