"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { FileContent } from "@/types";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-muted-foreground">에디터 로드 중…</div>,
});

function inferLanguage(path: string): string | undefined {
  if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
  if (path.endsWith(".js") || path.endsWith(".jsx")) return "javascript";
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".json") || path.endsWith(".jsonl")) return "json";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".yaml") || path.endsWith(".yml")) return "yaml";
  if (path.endsWith(".sh")) return "shell";
  return undefined;
}

export function MonacoModal({
  open,
  onClose,
  session,
  path,
}: {
  open: boolean;
  onClose: () => void;
  session: string;
  path: string | null;
}) {
  const [content, setContent] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !path) return;
    setLoading(true);
    setContent(null);
    api.readFile(session, path)
      .then(setContent)
      .catch(() => toast.error(`${path} 파일을 읽지 못했습니다`))
      .finally(() => setLoading(false));
  }, [open, session, path]);

  const language = useMemo(() => (path ? inferLanguage(path) : undefined), [path]);
  const isMarkdown = path?.endsWith(".md");

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed inset-x-4 top-8 bottom-8 z-50 mx-auto flex max-w-5xl flex-col rounded-md border border-border bg-card shadow-xl"
          onEscapeKeyDown={onClose}
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <Dialog.Title className="truncate text-sm font-medium">{path}</Dialog.Title>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  if (content?.content) {
                    navigator.clipboard.writeText(content.content);
                    toast.success("복사 완료");
                  }
                }}
                className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
              >
                <Copy className="h-3 w-3" /> 복사
              </button>
              <button
                type="button"
                onClick={onClose}
                aria-label="닫기"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-hidden">
            {loading && <div className="grid h-full place-items-center text-sm text-muted-foreground">불러오는 중…</div>}
            {!loading && content?.binary && <div className="p-6 text-sm">바이너리 파일 ({(content.size / 1024).toFixed(1)} KB)</div>}
            {!loading && content && !content.binary && isMarkdown && (
              <div className="prose prose-sm dark:prose-invert max-w-none overflow-auto p-6">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                  {content.content ?? ""}
                </ReactMarkdown>
              </div>
            )}
            {!loading && content && !content.binary && !isMarkdown && (
              <MonacoEditor
                height="100%"
                language={language}
                value={content.content ?? ""}
                theme="vs-dark"
                options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, wordWrap: "on" }}
              />
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
