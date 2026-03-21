"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { authFetch, getAuthHeader } from "@/lib/supabase/access-token";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type AgentStage = {
  stage: string;
  status: "pending" | "running" | "success" | "failed" | "skipped";
  output?: string;
  error?: string;
  time_ms?: number;
};

type AgentExecution = {
  id: string;
  stage: string;
  agent_type: string;
  status: string;
  output_result?: string;
  explanation?: string;
  error_message?: string;
  execution_time_ms?: number;
  created_at: string;
};

const TEST_PROMPTS = [
  "Create a project called my-api",
  "Add JWT authentication to my-api",
  "Check status of all projects",
  "Add unit tests to my-api",
  "Fix the login bug in my-api",
];

export function VoiceRecorder() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [testInput, setTestInput] = useState("");
  const [showTestPanel, setShowTestPanel] = useState(false);

  // Response State
  const [transcript, setTranscript] = useState<string | null>(null);
  const [intent, setIntent] = useState<Record<string, unknown> | null>(null);
  const [actionResult, setActionResult] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<string | null>(null);

  // Agent Pipeline State
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [agentStages, setAgentStages] = useState<AgentStage[]>([]);
  const [pollingTaskId, setPollingTaskId] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const router = useRouter();

  // Poll for agent status updates
  const pollAgentStatus = useCallback(async (taskId: string) => {
    try {
      const res = await authFetch(`${backendUrl}/api/agent/status/${taskId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.executions) {
        // Derive stages from executions
        const stages: AgentStage[] = data.executions.map((ex: AgentExecution) => ({
          stage: ex.stage,
          status: ex.status as AgentStage["status"],
          output: ex.output_result,
          error: ex.error_message,
          time_ms: ex.execution_time_ms,
        }));
        setAgentStages(stages);
        // Check if pipeline is complete
        const allDone = stages.every(
          (s: AgentStage) => s.status === "success" || s.status === "failed"
        );
        if (allDone && stages.length >= 2) {
          setAgentStatus("complete");
          setPollingTaskId(null);
        }
      }
    } catch {
      // silently retry
    }
  }, [backendUrl]);

  useEffect(() => {
    if (!pollingTaskId) return;
    const interval = setInterval(() => pollAgentStatus(pollingTaskId), 2000);
    return () => clearInterval(interval);
  }, [pollingTaskId, pollAgentStatus]);

  const startRecording = async () => {
    try {
      setTranscript(null);
      setIntent(null);
      setActionResult(null);
      setDebugInfo(null);
      setAgentStatus(null);
      setAgentStages([]);
      setPollingTaskId(null);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        await handleUpload(audioBlob);
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      alert("Microphone access denied. Please allow permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }
  };

  const handleUpload = async (audioBlob: Blob) => {
    setLoading(true);
    const auth = await getAuthHeader();
    if (!auth) {
      alert("Session unavailable. Please sign in again.");
      setLoading(false);
      return;
    }

    const formData = new FormData();
    formData.append("file", audioBlob, "audio.webm");

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
    try {
      const response = await fetch(`${backendUrl}/transcribe`, {
        method: "POST",
        headers: {
          ...auth,
        },
        body: formData,
      });

      const result = await response.json();
      if (response.ok) {
        setTranscript(result.transcript);
        setIntent(result.intent);
        setActionResult(result.action_result);
        setDebugInfo(`Context: ${result.context_projects_count} projects loaded`);

        // Start agent pipeline tracking
        if (result.agent_status) {
          setAgentStatus(result.agent_status);
          const taskId = result.created?.task_id || result.logged_task_id;
          if (taskId) {
            setPollingTaskId(taskId);
            // Show initial "dispatching" stage
            setAgentStages([
              { stage: "refine", status: "running", output: "Refining prompt..." },
            ]);
          }
        }

        router.refresh();
      } else {
        console.error("Server Error:", result);
        setActionResult(`Error: ${result.message}`);
      }
    } catch (error) {
      console.error("Network error:", error);
      setActionResult("Error: Could not connect to backend.");
    } finally {
      setLoading(false);
    }
  };

  const handleTestCommand = async (text: string) => {
    setLoading(true);
    setTranscript(null);
    setIntent(null);
    setActionResult(null);
    setDebugInfo(null);
    setAgentStatus(null);
    setAgentStages([]);
    setPollingTaskId(null);

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
    try {
      const auth = await getAuthHeader();
      const response = await fetch(`${backendUrl}/transcribe-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ text }),
      });

      const result = await response.json();
      if (response.ok) {
        setTranscript(result.transcript);
        setIntent(result.intent);
        setActionResult(result.action_result);
        setDebugInfo(`Context: ${result.context_projects_count} projects loaded`);

        if (result.agent_status) {
          setAgentStatus(result.agent_status);
          const taskId = result.created?.task_id || result.logged_task_id;
          if (taskId) {
            setPollingTaskId(taskId);
            setAgentStages([
              { stage: "refine", status: "running", output: "Refining prompt..." },
            ]);
          }
        }
        router.refresh();
      } else {
        setActionResult(`Error: ${result.message}`);
      }
    } catch {
      setActionResult("Error: Could not connect to backend.");
    } finally {
      setLoading(false);
    }
  };

  const stageIcon = (status: string) => {
    switch (status) {
      case "success":
        return (
          <svg className="w-4 h-4 text-green-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
          </svg>
        );
      case "failed":
        return (
          <svg className="w-4 h-4 text-red-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
          </svg>
        );
      case "running":
        return (
          <div className="w-4 h-4 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin" />
        );
      default:
        return <div className="w-4 h-4 rounded-full bg-gray-600" />;
    }
  };

  const stageLabel = (stage: string) => {
    switch (stage) {
      case "refine": return "Prompt Refiner";
      case "dispatch": return "Task Dispatch";
      case "execute": return "Agent Executor";
      case "terminal": return "Terminal Execution";
      case "complete": return "Complete";
      default: return stage;
    }
  };

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      {/* --- ACTION AREA --- */}
      <div className="flex items-center gap-5 p-5 border-b border-border">
        {/* Record Button */}
        <button
          onClick={isRecording ? stopRecording : startRecording}
          disabled={loading}
          className={`
            w-16 h-16 shrink-0 rounded-full flex items-center justify-center transition-all duration-200 shadow-lg
            ${isRecording
              ? "bg-red-500/10 text-red-500 border-2 border-red-500 scale-110"
              : "bg-supabase-green text-black hover:bg-supabase-green-dark hover:scale-105"
            }
            ${loading ? "opacity-50 cursor-not-allowed animate-pulse" : ""}
          `}
        >
          {loading ? (
            <div className="w-6 h-6 border-3 border-current border-t-transparent rounded-full animate-spin" />
          ) : isRecording ? (
            <div className="w-5 h-5 bg-current rounded-sm" />
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-7 h-7">
              <path d="M8.25 4.5a3.75 3.75 0 117.5 0v8.25a3.75 3.75 0 11-7.5 0V4.5z" />
              <path d="M6 10.5a.75.75 0 01.75.75v1.5a5.25 5.25 0 1010.5 0v-1.5a.75.75 0 011.5 0v1.5a6.751 6.751 0 01-6 6.709v2.291h3a.75.75 0 010 1.5h-7.5a.75.75 0 010-1.5h3v-2.291a6.751 6.751 0 01-6-6.709v-1.5A.75.75 0 016 10.5z" />
            </svg>
          )}
        </button>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">Voice Command</p>
          <p className="text-xs text-muted-foreground font-mono">
            {loading ? "Processing audio..." : isRecording ? "Listening — tap to stop" : "Tap the mic to issue a command"}
          </p>
        </div>

        {/* Status Light */}
        <div className={`w-2.5 h-2.5 rounded-full shrink-0 transition-all duration-300 ${
          isRecording
            ? "bg-red-500 animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.6)]"
            : agentStatus === "dispatching"
            ? "bg-yellow-500 animate-pulse shadow-[0_0_10px_rgba(234,179,8,0.6)]"
            : agentStatus === "complete"
            ? "bg-emerald-500 shadow-[0_0_10px_rgba(34,197,94,0.6)]"
            : "bg-muted-foreground/30"
        }`} />
      </div>

      {/* --- DEV TEST PANEL --- */}
      <div className="border-b border-border">
        <button
          onClick={() => setShowTestPanel(!showTestPanel)}
          className="w-full px-5 py-2 flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <span className="font-mono">DEV: Send text command</span>
          <span>{showTestPanel ? "\u25B2" : "\u25BC"}</span>
        </button>

        {showTestPanel && (
          <div className="px-5 pb-4 space-y-3">
            <div className="flex gap-2">
              <Input
                value={testInput}
                onChange={(e) => setTestInput(e.target.value)}
                placeholder="Type a command..."
                className="text-sm"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && testInput.trim() && !loading) {
                    handleTestCommand(testInput.trim());
                  }
                }}
              />
              <Button
                size="sm"
                onClick={() => handleTestCommand(testInput.trim())}
                disabled={loading || !testInput.trim()}
              >
                Send
              </Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {TEST_PROMPTS.map((prompt) => (
                <Button
                  key={prompt}
                  variant="outline"
                  size="sm"
                  className="text-xs h-7"
                  disabled={loading}
                  onClick={() => handleTestCommand(prompt)}
                >
                  {prompt}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* --- AGENT OUTPUT CONSOLE --- */}
      {(transcript || intent) ? (
        <div className="flex-1 overflow-auto">
          <CardHeader className="bg-black/40 px-4 py-2 border-b border-white/5 flex flex-row items-center justify-between space-y-0 pb-2">
            <span className="text-xs font-mono text-gray-500">AGENT LOGS</span>
            {debugInfo && <span className="text-xs font-mono text-gray-600">{debugInfo}</span>}
          </CardHeader>

          <CardContent className="p-6 space-y-6">

            {/* 1. The Ear (Transcript) */}
            {transcript && (
              <div className="space-y-1 animate-fade-in-up">
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">User Input (Whisper)</p>
                <p className="text-lg text-white font-medium">&quot;{transcript}&quot;</p>
              </div>
            )}

            {/* 2. The Brain (Intent) */}
            {intent && (
              <div className="space-y-2 animate-fade-in-up" style={{ animationDelay: "0.15s" }}>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Detected Intent (Bedrock)</p>
                <div className="bg-black/30 p-3 rounded-md font-mono text-sm text-blue-300 border-l-2 border-blue-500">
                  <p>Type: <span className="text-white">{intent.intent as string}</span></p>
                  {!!intent.project_name && <p>Project: <span className="text-white">{String(intent.project_name)}</span></p>}
                  {!!intent.task_description && <p>Task: <span className="text-white">{String(intent.task_description)}</span></p>}
                </div>
              </div>
            )}

            {/* 3. The Hands (Action Result) */}
            {actionResult && (
              <div className="space-y-2 animate-fade-in-up" style={{ animationDelay: "0.3s" }}>
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Execution Result (SQLite)</p>
                <div className="bg-supabase-green/10 p-4 rounded-md border border-supabase-green/20">
                  <p className="text-supabase-green font-mono text-sm flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 shrink-0">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                    </svg>
                    {actionResult}
                  </p>
                </div>
              </div>
            )}

            {/* 4. Agent Pipeline Stages */}
            {agentStages.length > 0 && (
              <div className="space-y-3 animate-fade-in-up" style={{ animationDelay: "0.45s" }}>
                <div className="flex items-center gap-2">
                  <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Agent Pipeline</p>
                  {agentStatus === "dispatching" && (
                    <span className="text-xs text-yellow-400 font-mono animate-pulse">● RUNNING</span>
                  )}
                  {agentStatus === "complete" && (
                    <span className="text-xs text-green-400 font-mono">● COMPLETE</span>
                  )}
                </div>

                {/* Pipeline visualization */}
                <div className="relative">
                  {/* Connecting line */}
                  <div className="absolute left-[9px] top-6 bottom-2 w-px bg-gray-700" />

                  <div className="space-y-0">
                    {agentStages.map((stage, i) => (
                      <div
                        key={`${stage.stage}-${i}`}
                        className="relative flex items-start gap-3 py-2 animate-stage-enter"
                        style={{ animationDelay: `${i * 0.2}s` }}
                      >
                        {/* Stage icon */}
                        <div className="relative z-10 mt-0.5 shrink-0">
                          {stageIcon(stage.status)}
                        </div>

                        {/* Stage content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-300">
                              {stageLabel(stage.stage)}
                            </span>
                            {stage.time_ms !== undefined && (
                              <span className="text-xs text-gray-600 font-mono">
                                {stage.time_ms}ms
                              </span>
                            )}
                          </div>

                          {/* Output preview */}
                          {stage.output && stage.status === "success" && (
                            <div className="mt-1 text-xs font-mono text-gray-500 truncate max-w-full">
                              {stage.output.substring(0, 120)}
                              {stage.output.length > 120 ? "..." : ""}
                            </div>
                          )}

                          {/* Error */}
                          {stage.error && (
                            <div className="mt-1 text-xs font-mono text-red-400/80">
                              ⚠ {stage.error.substring(0, 100)}
                            </div>
                          )}

                          {/* Running shimmer */}
                          {stage.status === "running" && (
                            <div className="mt-1 h-2 w-32 rounded bg-gray-800 animate-shimmer" />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Workspace info */}
                {agentStatus === "complete" && (
                  <div className="mt-2 p-3 bg-black/30 rounded-md border border-gray-800 animate-fade-in-up">
                    {agentStages.some(s => s.stage === "terminal" && s.status === "success") ? (
                      <>
                        <p className="text-xs font-mono text-supabase-green">
                          ⚡ Terminal command queued for local agent
                        </p>
                        <p className="text-xs font-mono text-gray-600 mt-1">
                          Open the dashboard Terminal panel to see output once your local agent is running.
                        </p>
                      </>
                    ) : agentStages.some(s => s.stage === "terminal" && s.status === "skipped") ? (
                      <>
                        <p className="text-xs font-mono text-gray-500">
                          📁 Task dispatched to <span className="text-gray-400">~/Desktop/agent-workspace/tasks/</span>
                        </p>
                        <p className="text-xs font-mono text-yellow-400/60 mt-1">
                          💡 Enable Terminal Access in the dashboard for auto-execution.
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-xs font-mono text-gray-500">
                          Task dispatched. Check the Unified Command Center timeline for output.
                        </p>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-8">
          <p className="text-sm text-muted-foreground">No commands yet. Record a voice command to get started.</p>
        </div>
      )}
    </Card>
  );
}
