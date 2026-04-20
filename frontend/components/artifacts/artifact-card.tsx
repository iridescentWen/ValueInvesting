"use client";

import { PinIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  type Artifact,
  type ArtifactType,
  getArtifactComponent,
} from "./registry";

export function ArtifactCard<T extends ArtifactType>({
  artifact,
  onPin,
  className,
}: {
  artifact: Artifact<T>;
  onPin?: (a: Artifact<T>) => void;
  className?: string;
}) {
  const Component = getArtifactComponent(artifact.type);
  if (!Component) {
    return (
      <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        未知 artifact: <code className="font-mono">{artifact.type}</code>
      </div>
    );
  }

  return (
    <div className={cn("group relative", className)}>
      <Component data={artifact.data} />
      {onPin && (
        <Button
          aria-label="Pin to workspace"
          className="absolute right-2 top-2 opacity-0 transition-opacity group-hover:opacity-100"
          onClick={() => onPin(artifact)}
          size="icon-xs"
          variant="ghost"
        >
          <PinIcon />
        </Button>
      )}
    </div>
  );
}
