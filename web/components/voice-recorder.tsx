// web/components/voice-recorder.tsx
"use client";

import { useState, useRef } from "react";
import { createClient } from "@/lib/supabase/client";

export function VoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  
  // Response State
  const [transcript, setTranscript] = useState<string | null>(null);
  const [intent, setIntent] = useState<any | null>(null);
  const [actionResult, setActionResult] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const supabase = createClient();

  const startRecording = async () => {
    try {
      // Reset previous state
      setTranscript(null);
      setIntent(null);
      setActionResult(null);
      setDebugInfo(null);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
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
    
    // CHANGE 1: Force a session refresh to ensure the token is valid
    const { data, error } = await supabase.auth.refreshSession();
    const session = data.session;

    if (!session || error) {
      console.error("Auth Error:", error);
      alert("Session expired. Please log in again.");
      setLoading(false);
      // Optional: Redirect to login
      // window.location.href = '/login'; 
      return;
    }

    console.log("Using Token:", session.access_token.substring(0, 10) + "..."); // Debug log

    const formData = new FormData();
    formData.append("file", audioBlob, "audio.webm");

    try {
      const response = await fetch("http://localhost:8000/transcribe", {
        method: "POST",
        headers: {
          // CHANGE 2: Ensure the Bearer prefix is correct
          Authorization: `Bearer ${session.access_token}`,
        },
        body: formData,
      });

      const result = await response.json();

      if (response.ok) {
        setTranscript(result.transcript);
        setIntent(result.intent);
        setActionResult(result.action_result);
        setDebugInfo(`Context: ${result.context_projects_count} projects loaded`);
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

  return (
    <div className="w-full max-w-2xl mx-auto flex flex-col items-center gap-8">
      
      {/* --- ACTION AREA --- */}
      <div className="flex flex-col items-center gap-4">
        {/* Status Light */}
        <div className={`w-3 h-3 rounded-full transition-all duration-300 ${isRecording ? "bg-red-500 animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.6)]" : "bg-gray-700"}`} />

        {/* Record Button */}
        <button
          onClick={isRecording ? stopRecording : startRecording}
          disabled={loading}
          className={`
            w-24 h-24 rounded-full flex items-center justify-center transition-all duration-200 shadow-2xl
            ${isRecording 
              ? "bg-red-500/10 text-red-500 border-2 border-red-500 scale-110" 
              : "bg-supabase-green text-black hover:bg-supabase-green-dark hover:scale-105"
            }
            ${loading ? "opacity-50 cursor-not-allowed animate-pulse" : ""}
          `}
        >
          {loading ? (
            <div className="w-8 h-8 border-4 border-current border-t-transparent rounded-full animate-spin" />
          ) : isRecording ? (
            <div className="w-8 h-8 bg-current rounded-md" />
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-10 h-10">
              <path d="M8.25 4.5a3.75 3.75 0 117.5 0v8.25a3.75 3.75 0 11-7.5 0V4.5z" />
              <path d="M6 10.5a.75.75 0 01.75.75v1.5a5.25 5.25 0 1010.5 0v-1.5a.75.75 0 011.5 0v1.5a6.751 6.751 0 01-6 6.709v2.291h3a.75.75 0 010 1.5h-7.5a.75.75 0 010-1.5h3v-2.291a6.751 6.751 0 01-6-6.709v-1.5A.75.75 0 016 10.5z" />
            </svg>
          )}
        </button>
        
        <p className="text-gray-400 font-mono text-sm">
          {loading ? "Processing..." : isRecording ? "Listening..." : "Tap to Speak"}
        </p>
      </div>

      {/* --- AGENT OUTPUT CONSOLE --- */}
      {(transcript || intent) && (
        <div className="w-full bg-dark-card border border-dark-border rounded-xl overflow-hidden shadow-xl animate-in fade-in slide-in-from-bottom-4 duration-500">
          
          {/* Header */}
          <div className="bg-black/40 px-4 py-2 border-b border-white/5 flex items-center justify-between">
            <span className="text-xs font-mono text-gray-500">AGENT LOGS</span>
            {debugInfo && <span className="text-xs font-mono text-gray-600">{debugInfo}</span>}
          </div>

          <div className="p-6 space-y-6">
            
            {/* 1. The Ear (Transcript) */}
            {transcript && (
              <div className="space-y-1">
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">User Input (Whisper)</p>
                <p className="text-lg text-white font-medium">"{transcript}"</p>
              </div>
            )}

            {/* 2. The Brain (Intent) */}
            {intent && (
              <div className="space-y-2">
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Detected Intent (Bedrock)</p>
                <div className="bg-black/30 p-3 rounded-md font-mono text-sm text-blue-300 border-l-2 border-blue-500">
                  <p>Type: <span className="text-white">{intent.intent}</span></p>
                  {intent.project_name && <p>Project: <span className="text-white">{intent.project_name}</span></p>}
                </div>
              </div>
            )}

            {/* 3. The Hands (Action Result) */}
            {actionResult && (
              <div className="space-y-2">
                <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">Execution Result (SQLite)</p>
                <div className="bg-supabase-green/10 p-4 rounded-md border border-supabase-green/20">
                  <p className="text-supabase-green font-mono text-sm flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                    </svg>
                    {actionResult}
                  </p>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
}