"use client";

import { useState } from "react";
import type { FileNode } from "@/types";
import { ChevronRight, ChevronDown, File as FileIcon, Folder, FolderOpen } from "lucide-react";

function NodeRow({
  node,
  depth,
  onPick,
}: {
  node: FileNode;
  depth: number;
  onPick: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const pad = { paddingLeft: 8 + depth * 12 };
  if (node.is_dir) {
    return (
      <div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center gap-1 px-1 py-1 text-left text-xs text-foreground hover:bg-muted"
          style={pad}
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {open ? <FolderOpen className="h-3 w-3 text-brand" /> : <Folder className="h-3 w-3 text-brand" />}
          <span className="truncate">{node.name || "/"}</span>
        </button>
        {open && node.children?.map((child) => (
          <NodeRow key={child.path} node={child} depth={depth + 1} onPick={onPick} />
        ))}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onPick(node.path)}
      className="flex w-full items-center gap-1 px-1 py-1 text-left text-xs text-foreground hover:bg-muted"
      style={pad}
    >
      <span className="w-3" />
      <FileIcon className="h-3 w-3 text-muted-foreground" />
      <span className="truncate">{node.name}</span>
    </button>
  );
}

export function FileTreePane({ root, onPick }: { root: FileNode; onPick: (path: string) => void }) {
  return (
    <div className="h-full overflow-y-auto bg-card">
      <NodeRow node={root} depth={0} onPick={onPick} />
    </div>
  );
}
