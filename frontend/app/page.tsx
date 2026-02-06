"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, UserButton, SignInButton } from "@clerk/nextjs";
import { Upload, Youtube, ArrowRight, Loader2, Sparkles } from "lucide-react";
import axios from "axios";
import { cn } from "@/lib/utils";

const API_Base = "http://127.0.0.1:8000";

export default function Home() {
    const router = useRouter();
    const { isSignedIn, userId } = useAuth();
    const [activeTab, setActiveTab] = useState<"upload" | "youtube">("upload");
    const [loading, setLoading] = useState(false);
    const [url, setUrl] = useState("");
    const [file, setFile] = useState<File | null>(null);

    const handleProcess = async () => {
        if (!userId) return;

        setLoading(true);
        try {
            let response;
            const headers = { "X-User-ID": userId };

            if (activeTab === "youtube") {
                response = await axios.post(`${API_Base}/process-url`, { url }, { headers });
            } else {
                if (!file) return;
                const formData = new FormData();
                formData.append("file", file);
                response = await axios.post(`${API_Base}/upload`, formData, { headers });
            }

            const { task_id, video_id } = response.data;
            router.push(`/dashboard/${task_id}?video_id=${video_id}`);
        } catch (error) {
            console.error(error);
            alert("Something went wrong");
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="flex min-h-screen flex-col items-center justify-center p-4 sm:p-24 relative overflow-hidden">
            {/* Header */}
            <header className="absolute top-0 left-0 right-0 p-6 flex justify-between items-center z-20">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-6 h-6 text-primary" />
                    <span className="font-bold text-lg text-white">ClipGen AI</span>
                </div>
                <div className="flex items-center gap-4">
                    {isSignedIn ? (
                        <>
                            <a
                                href="/my-videos"
                                className="text-sm text-slate-400 hover:text-white transition-colors"
                            >
                                My Videos
                            </a>
                            <UserButton
                                appearance={{
                                    elements: {
                                        avatarBox: "w-9 h-9",
                                    },
                                }}
                            />
                        </>
                    ) : (
                        <SignInButton mode="modal">
                            <button className="px-4 py-2 bg-primary hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors">
                                Sign In
                            </button>
                        </SignInButton>
                    )}
                </div>
            </header>

            {/* Background Gradients */}
            <div className="absolute top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
                <div className="absolute -top-[20%] -left-[10%] w-[50%] h-[50%] rounded-full bg-violet-600/20 blur-[120px]" />
                <div className="absolute top-[40%] -right-[10%] w-[40%] h-[40%] rounded-full bg-indigo-600/20 blur-[120px]" />
            </div>

            <div className="z-10 w-full max-w-xl space-y-8 text-center">
                <div className="space-y-4">
                    <h1 className="text-4xl sm:text-6xl font-bold tracking-tighter bg-clip-text text-transparent bg-gradient-to-br from-white to-slate-400">
                        ClipGen AI
                    </h1>
                    <p className="text-slate-400 text-lg sm:text-xl">
                        Turn long videos into viral short clips with AI.
                    </p>
                </div>

                {!isSignedIn ? (
                    <div className="bg-card border border-border rounded-2xl p-8 text-center space-y-4">
                        <p className="text-slate-300">Sign in to start creating viral clips</p>
                        <SignInButton mode="modal">
                            <button className="px-6 py-3 bg-primary hover:bg-indigo-500 text-white font-medium rounded-xl transition-colors">
                                Get Started
                            </button>
                        </SignInButton>
                    </div>
                ) : (
                    <>
                        <div className="bg-card border border-border rounded-2xl p-2 w-full max-w-md mx-auto flex">
                            <button
                                onClick={() => setActiveTab("upload")}
                                className={cn(
                                    "flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl font-medium transition-all",
                                    activeTab === "upload"
                                        ? "bg-secondary text-white shadow-sm"
                                        : "text-slate-400 hover:text-white"
                                )}
                            >
                                <Upload className="w-4 h-4" />
                                Upload File
                            </button>
                            <button
                                onClick={() => setActiveTab("youtube")}
                                className={cn(
                                    "flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl font-medium transition-all",
                                    activeTab === "youtube"
                                        ? "bg-red-600/10 text-red-500 shadow-sm ring-1 ring-red-600/20"
                                        : "text-slate-400 hover:text-white"
                                )}
                            >
                                <Youtube className="w-4 h-4" />
                                YouTube
                            </button>
                        </div>

                        <div className="w-full max-w-md mx-auto bg-card border border-border rounded-2xl p-6 shadow-xl">
                            {activeTab === "youtube" ? (
                                <div className="space-y-4">
                                    <label className="text-sm font-medium text-slate-300 block text-left">
                                        YouTube URL
                                    </label>
                                    <input
                                        type="text"
                                        placeholder="https://youtube.com/watch?v=..."
                                        value={url}
                                        onChange={(e) => setUrl(e.target.value)}
                                        className="w-full bg-secondary border border-border rounded-xl px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                                    />
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <label className="text-sm font-medium text-slate-300 block text-left">
                                        Video File
                                    </label>
                                    <div className="border-2 border-dashed border-border rounded-xl p-8 flex flex-col items-center gap-3 hover:border-primary/50 hover:bg-secondary/50 transition-all cursor-pointer group relative">
                                        <input
                                            type="file"
                                            accept="video/*"
                                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                                            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                                        />
                                        <div className="p-3 bg-secondary rounded-full group-hover:scale-110 transition-transform">
                                            <Upload className="w-6 h-6 text-slate-400 group-hover:text-primary transition-colors" />
                                        </div>
                                        <div className="text-center">
                                            <p className="text-sm text-slate-300 font-medium">
                                                {file ? file.name : "Click to upload or drag and drop"}
                                            </p>
                                            <p className="text-xs text-slate-500 mt-1">
                                                MP4, MOV up to 500MB
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <button
                                onClick={handleProcess}
                                disabled={loading || (activeTab === "youtube" && !url) || (activeTab === "upload" && !file)}
                                className="w-full mt-6 bg-primary hover:bg-indigo-500 text-white font-medium py-3 rounded-xl flex items-center justify-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Processing...
                                    </>
                                ) : (
                                    <>
                                        Generate Clips
                                        <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                                    </>
                                )}
                            </button>
                        </div>
                    </>
                )}
            </div>
        </main>
    );
}
