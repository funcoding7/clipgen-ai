"use client";

import { useEffect, useState } from "react";
import { useAuth, UserButton } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { Sparkles, Video, Clock, CheckCircle2, XCircle, Loader2, Plus } from "lucide-react";
import axios from "axios";
import { cn } from "@/lib/utils";

const API_Base = "http://127.0.0.1:8000";

interface VideoItem {
    id: string;
    filename: string;
    source_url: string | null;
    status: string;
    task_id: string | null;
    created_at: string;
    clips: { id: string; filename: string; reason: string | null }[];
}

export default function MyVideosPage() {
    const { userId } = useAuth();
    const router = useRouter();
    const [videos, setVideos] = useState<VideoItem[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchVideos = async () => {
            if (!userId) return;

            try {
                const { data } = await axios.get(`${API_Base}/videos`, {
                    headers: { "X-User-ID": userId },
                });
                setVideos(data);
            } catch (error) {
                console.error("Failed to fetch videos:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchVideos();
    }, [userId]);

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "COMPLETED":
                return <CheckCircle2 className="w-4 h-4 text-green-500" />;
            case "FAILED":
                return <XCircle className="w-4 h-4 text-red-500" />;
            case "PROCESSING":
                return <Loader2 className="w-4 h-4 text-amber-500 animate-spin" />;
            default:
                return <Clock className="w-4 h-4 text-slate-400" />;
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case "COMPLETED":
                return "text-green-500 bg-green-500/10";
            case "FAILED":
                return "text-red-500 bg-red-500/10";
            case "PROCESSING":
                return "text-amber-500 bg-amber-500/10";
            default:
                return "text-slate-400 bg-slate-400/10";
        }
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    };

    return (
        <main className="min-h-screen bg-background">
            {/* Header */}
            <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
                    <a href="/" className="flex items-center gap-2">
                        <Sparkles className="w-6 h-6 text-primary" />
                        <span className="font-bold text-lg text-white">ClipGen AI</span>
                    </a>
                    <div className="flex items-center gap-4">
                        <a
                            href="/"
                            className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            <Plus className="w-4 h-4" />
                            New Video
                        </a>
                        <UserButton
                            appearance={{
                                elements: {
                                    avatarBox: "w-9 h-9",
                                },
                            }}
                        />
                    </div>
                </div>
            </header>

            {/* Content */}
            <div className="max-w-7xl mx-auto px-6 py-12">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-white">My Videos</h1>
                    <p className="text-slate-400 mt-2">
                        View and manage your processed videos
                    </p>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-24">
                        <Loader2 className="w-8 h-8 text-primary animate-spin" />
                    </div>
                ) : videos.length === 0 ? (
                    <div className="text-center py-24 space-y-4">
                        <Video className="w-16 h-16 text-slate-600 mx-auto" />
                        <h2 className="text-xl font-semibold text-white">No videos yet</h2>
                        <p className="text-slate-400">
                            Upload your first video to get started
                        </p>
                        <a
                            href="/"
                            className="inline-flex items-center gap-2 px-6 py-3 bg-primary hover:bg-indigo-500 text-white font-medium rounded-xl transition-colors"
                        >
                            <Plus className="w-4 h-4" />
                            Create First Clip
                        </a>
                    </div>
                ) : (
                    <div className="grid gap-4">
                        {videos.map((video) => (
                            <div
                                key={video.id}
                                className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 transition-all cursor-pointer group"
                                onClick={() => {
                                    if (video.task_id) {
                                        router.push(`/dashboard/${video.task_id}?video_id=${video.id}`);
                                    }
                                }}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-4">
                                        <div className="p-3 bg-secondary rounded-xl">
                                            <Video className="w-6 h-6 text-slate-400" />
                                        </div>
                                        <div>
                                            <h3 className="font-semibold text-white group-hover:text-primary transition-colors">
                                                {video.filename}
                                            </h3>
                                            <p className="text-sm text-slate-500">
                                                {formatDate(video.created_at)}
                                                {video.source_url && " • YouTube"}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        {video.clips.length > 0 && (
                                            <span className="text-sm text-slate-400">
                                                {video.clips.length} clips
                                            </span>
                                        )}
                                        <span
                                            className={cn(
                                                "flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium",
                                                getStatusColor(video.status)
                                            )}
                                        >
                                            {getStatusIcon(video.status)}
                                            {video.status}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </main>
    );
}
