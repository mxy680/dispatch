"use client";

import dynamic from "next/dynamic";

const TerminalConsole = dynamic(
  () => import("@/components/terminal-console").then((m) => m.TerminalConsole),
  { ssr: false }
);

type Props = {
  projects: { id: string; name: string }[];
};

export function TerminalConsoleWrapper({ projects }: Props) {
  return <TerminalConsole projects={projects} />;
}
