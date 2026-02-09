// web/components/voice-recorder.tsx
"use client";

import { useState, useRef } from "react";
import { createClient } from "@/lib/supabase/client";

export function VoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const supabase = createClient();

  const startRecording = async () => {
    try {
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
      setTranscript(null);
    } catch (err) {
      console.error("Error accessing microphone:", err);
      alert("Microphone access denied. Please allow permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      // Stop all audio tracks to turn off the red dot in browser tab
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }
  };

  const handleUpload = async (audioBlob: Blob) => {
    setLoading(true);
    
    // 1. Get the current user's token for security
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
      alert("You must be logged in to use the assistant.");
      setLoading(false);
      return;
    }

    // 2. Prepare the form data
    const formData = new FormData();
    // Note: 'audio.webm' filename is important for the backend to recognize it
    formData.append("file", audioBlob, "audio.webm");

    try {
      // 3. Send to Python Backend
      const response = await fetch("http://localhost:8000/transcribe", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
        body: formData,
      });

      const result = await response.json();

      if (response.ok) {
        setTranscript(result.transcript);
      } else {
        console.error("Transcription failed:", result);
        alert("Error: " + (result.detail || "Transcription failed"));
      }
    } catch (error) {
      console.error("Network error:", error);
      alert("Could not connect to the Python server. Is it running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto p-6 bg-dark-card border border-dark-border rounded-xl shadow-lg flex flex-col items-center gap-6">
      
      {/* Status Indicator */}
      <div className={`w-4 h-4 rounded-full transition-colors duration-300 ${isRecording ? "bg-red-500 animate-pulse" : "bg-gray-600"}`} />

      {/* Main Action Button */}
      <button
        onClick={isRecording ? stopRecording : startRecording}
        disabled={loading}
        className={`w-20 h-20 rounded-full flex items-center justify-center transition-all duration-200 shadow-xl
          ${isRecording 
            ? "bg-red-500/20 text-red-500 border-2 border-red-500 hover:scale-105" 
            : "bg-supabase-green text-black hover:bg-supabase-green-dark hover:scale-105"
          }
          ${loading ? "opacity-50 cursor-not-allowed" : ""}
        `}
      >
        {loading ? (
          // Simple Spinner
          <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : isRecording ? (
          // Stop Icon
          <div className="w-6 h-6 bg-current rounded-sm" />
        ) : (
          // Mic Icon
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-8 h-8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 1.5a3 3 0 013 3v4.5a3 3 0 01-6 0v-4.5a3 3 0 013-3z" />
          </svg>
        )}
      </button>

      {/* Instructions / Status Text */}
      <p className="text-gray-400 text-sm font-medium">
        {loading ? "Transcribing..." : isRecording ? "Listening..." : "Tap to Speak"}
      </p>

      {/* Transcript Output */}
      {transcript && (
        <div className="w-full mt-4 p-4 bg-black/30 rounded-lg border border-white/10 animate-in fade-in slide-in-from-bottom-2">
          <p className="text-gray-300 italic">"{transcript}"</p>
        </div>
      )}
    </div>
  );
}