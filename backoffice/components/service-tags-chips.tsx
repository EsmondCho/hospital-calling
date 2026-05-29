import { Badge } from "@/components/ui/badge";

export function ServiceTagsChips({ tags }: { tags: string[] | null | undefined }) {
  if (!tags || tags.length === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <Badge key={t} variant="outline" className="text-[10px]">
          {t}
        </Badge>
      ))}
    </div>
  );
}
