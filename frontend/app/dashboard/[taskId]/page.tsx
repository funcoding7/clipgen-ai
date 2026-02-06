"use client";

import { useEffect, useState, use } from "react";
import { useAuth, UserButton } from "@clerk/nextjs";
import { Loader2, Search, CheckCircle2, Clock, Sparkles, ArrowLeft, Download, Smartphone } from "lucide-react";
import axios from "axios";
import { cn } from "@/lib/utils";

const API_Base = "http://127.0.0.1:8000";

interface ClipData {
    id: string;
    filename: string;
    s3_key: string | null;
    download_url: string | null;
    shorts_s3_key: string | null;
    shorts_download_url: string | null;
    reason: string | null;
    start_time: number | null;
    end_time: number | null;
}

interface VideoData {
    id: string;
    filename: string;
    status: string;
    clips: ClipData[];
}

export default function Dashboard({
    params,
    searchParams,
}: {
    params: Promise<{ taskId: string }>;
    searchParams: Promise<{ video_id: string }>;
}) {
    const { taskId } = use(params);
    const { video_id } = use(searchParams);
    const { userId } = useAuth();

    const [status, setStatus] = useState<"PENDING" | "STARTED" | "SUCCESS" | "FAILURE">("PENDING");
    const [videoData, setVideoData] = useState<VideoData | null>(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<{ start: number; end: number } | null>(null);
    const [isSearching, setIsSearching] = useState(false);
    const [convertingClips, setConvertingClips] = useState<Set<string>>(new Set());
    const [shortsUrls, setShortsUrls] = useState<Record<string, string>>({});

    // Poll task status
    useEffect(() => {
        const pollStatus = async () => {
            try {
                const { data } = await axios.get(`${API_Base}/task/${taskId}`);
                console.log("Polling...", data);
                setStatus(data.status);

                if (data.status === "SUCCESS" || data.status === "FAILURE") {
                    // Fetch video details with presigned URLs
                    await fetchVideoDetails();
                } else {
                    setTimeout(pollStatus, 2000);
                }
            } catch (e) {
                console.error(e);
            }
        };

        if (status !== "SUCCESS" && status !== "FAILURE") {
            pollStatus();
        }
    }, [taskId, status]);

    // Fetch video details with S3 presigned URLs
    const fetchVideoDetails = async () => {
        if (!userId) return;

        try {
            const { data } = await axios.get(`${API_Base}/videos/${video_id}`, {
                headers: { "X-User-ID": userId },
            });
            setVideoData(data);

            // Initialize shorts URLs from existing data
            const existingShorts: Record<string, string> = {};
            data.clips.forEach((clip: ClipData) => {
                if (clip.shorts_download_url) {
                    existingShorts[clip.id] = clip.shorts_download_url;
                }
            });
            setShortsUrls(existingShorts);
        } catch (e) {
            console.error("Failed to fetch video details:", e);
        }
    };

    const handleSearch = async () => {
        if (!searchQuery) return;
        setIsSearching(true);
        try {
            const { data } = await axios.get(`${API_Base}/search/${video_id}`, {
                params: { q: searchQuery },
            });
            setSearchResults(data.relevant_segments);
        } catch (e) {
            console.error(e);
        } finally {
            setIsSearching(false);
        }
    };

    const handleConvertToShorts = async (clipId: string) => {
        if (!userId) return;

        setConvertingClips(prev => new Set(prev).add(clipId));

        try {
            const { data } = await axios.post(
                `${API_Base}/clips/${clipId}/convert-shorts`,
                {},
                { headers: { "X-User-ID": userId } }
            );

            if (data.status === "already_converted") {
                setShortsUrls(prev => ({ ...prev, [clipId]: data.shorts_download_url }));
                setConvertingClips(prev => {
                    const next = new Set(prev);
                    next.delete(clipId);
                    return next;
                });
            } else if (data.status === "processing") {
                // Poll for completion
                const pollShortsStatus = async () => {
                    try {
                        const result = await axios.get(
                            `${API_Base}/clips/${clipId}/shorts`,
                            { headers: { "X-User-ID": userId } }
                        );

                        if (result.data.status === "ready") {
                            setShortsUrls(prev => ({ ...prev, [clipId]: result.data.shorts_download_url }));
                            setConvertingClips(prev => {
                                const next = new Set(prev);
                                next.delete(clipId);
                                return next;
                            });
                        } else {
                            setTimeout(pollShortsStatus, 2000);
                        }
                    } catch (e) {
                        console.error(e);
                        setConvertingClips(prev => {
                            const next = new Set(prev);
                            next.delete(clipId);
                            return next;
                        });
                    }
                };
                setTimeout(pollShortsStatus, 3000);
            }
        } catch (e) {
            console.error("Failed to convert to shorts:", e);
            setConvertingClips(prev => {
                const next = new Set(prev);
                next.delete(clipId);
                return next;
            });
        }
    };

    const formatTime = (s: number) => {
        const mins = Math.floor(s / 60);
        const secs = Math.floor(s % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    };

    const clips = videoData?.clips || [];

    return (
        <main className="min-h-screen bg-background">
            {/* Background */}
            <div className="fixed top-0 left-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
                <div className="absolute -top-[20%] right-[10%] w-[50%] h-[50%] rounded-full bg-violet-900/10 blur-[120px]" />
            </div>

            {/* Header */}
            <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
                    <div className="flex items-center gap-4">
                        <a href="/" className="flex items-center gap-2">
                            <Sparkles className="w-6 h-6 text-primary" />
                            <span className="font-bold text-lg text-white">ClipGen AI</span>
                        </a>
                        <span className="text-slate-600">|</span>
                        <a
                            href="/my-videos"
                            className="flex items-center gap-1 text-sm text-slate-400 hover:text-white transition-colors"
                        >
                            <ArrowLeft className="w-4 h-4" />
                            My Videos
                        </a>
                    </div>
                    <div className="flex items-center gap-4">
                        <div
                            className={cn(
                                "flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium",
                                status === "SUCCESS"
                                    ? "bg-green-500/10 text-green-500"
                                    : status === "FAILURE"
                                        ? "bg-red-500/10 text-red-500"
                                        : "bg-amber-500/10 text-amber-500"
                            )}
                        >
                            <div
                                className={cn(
                                    "w-2 h-2 rounded-full",
                                    status === "SUCCESS"
                                        ? "bg-green-500"
                                        : status === "FAILURE"
                                            ? "bg-red-500"
                                            : "bg-amber-500 animate-pulse"
                                )}
                            />
                            {status === "SUCCESS" ? "Completed" : status === "FAILURE" ? "Failed" : "Processing..."}
                        </div>
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

            <div className="max-w-7xl mx-auto px-6 py-12 space-y-12">
                {/* Processing State */}
                {status !== "SUCCESS" && status !== "FAILURE" && (
                    <div className="text-center py-24 space-y-6">
                        <div className="relative w-24 h-24 mx-auto">
                            <div className="absolute inset-0 border-4 border-secondary rounded-full" />
                            <div className="absolute inset-0 border-4 border-t-primary border-r-primary border-b-transparent border-l-transparent rounded-full animate-spin" />
                            <Loader2 className="absolute inset-0 m-auto w-8 h-8 text-primary animate-pulse" />
                        </div>
                        <div className="space-y-2">
                            <h2 className="text-2xl font-semibold text-white">Analyzing Video Content...</h2>
                            <p className="text-slate-400 max-w-md mx-auto">
                                We are transcribing the audio, identifying viral hooks with Gemini Flash 2.0, and
                                generating clips. This usually takes 1-2 minutes.
                            </p>
                        </div>
                    </div>
                )}

                {/* Failure State */}
                {status === "FAILURE" && (
                    <div className="text-center py-24 space-y-6">
                        <div className="text-red-500">
                            <h2 className="text-2xl font-semibold">Processing Failed</h2>
                            <p className="text-slate-400 mt-2">Something went wrong. Please try again.</p>
                        </div>
                    </div>
                )}

                {/* Results */}
                {status === "SUCCESS" && clips.length > 0 && (
                    <div className="space-y-12">
                        {/* Search */}
                        <div className="max-w-2xl mx-auto space-y-4">
                            <h3 className="text-center text-xl font-semibold text-white">
                                Find a specific moment
                            </h3>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Search e.g., 'When they talk about AI future'..."
                                    className="flex-1 bg-secondary border border-border rounded-xl px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-primary/50"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                                />
                                <button
                                    onClick={handleSearch}
                                    disabled={isSearching}
                                    className="bg-primary hover:bg-indigo-500 text-white px-6 rounded-xl font-medium transition-colors disabled:opacity-50"
                                >
                                    {isSearching ? (
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                    ) : (
                                        <Search className="w-5 h-5" />
                                    )}
                                </button>
                            </div>

                            {searchResults && (
                                <div className="bg-card border border-primary/20 rounded-xl p-4 flex items-center gap-4">
                                    <div className="p-3 bg-primary/10 rounded-full text-primary">
                                        <Clock className="w-5 h-5" />
                                    </div>
                                    <div>
                                        <p className="text-sm text-slate-400 font-medium">Found relevant segment</p>
                                        <p className="text-lg font-bold text-white">
                                            {formatTime(searchResults.start)} - {formatTime(searchResults.end)}
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Clips Grid */}
                        <div className="space-y-6">
                            <div className="flex items-center gap-3">
                                <CheckCircle2 className="w-6 h-6 text-green-500" />
                                <h2 className="text-2xl font-bold text-white">
                                    Start Posting! ({clips.length} Clips)
                                </h2>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                {clips.map((clip, idx) => (
                                    <div
                                        key={clip.id || idx}
                                        className="group bg-card border border-border rounded-2xl overflow-hidden hover:border-primary/50 transition-all hover:shadow-2xl hover:shadow-primary/10"
                                    >
                                        <div className="aspect-9/16 bg-black relative">
                                            {clip.download_url ? (
                                                <video
                                                    src={clip.download_url}
                                                    controls
                                                    className="w-full h-full object-cover"
                                                />
                                            ) : (
                                                <div className="flex items-center justify-center h-full text-slate-500">
                                                    Video unavailable
                                                </div>
                                            )}
                                        </div>
                                        <div className="p-5 space-y-3">
                                            <div className="flex items-start justify-between gap-4">
                                                <h4 className="font-semibold text-white leading-tight line-clamp-2">
                                                    {clip.reason || "Clip"}
                                                </h4>
                                                <span className="text-xs font-mono text-slate-500 bg-secondary px-2 py-1 rounded-md border border-border">
                                                    #{idx + 1}
                                                </span>
                                            </div>

                                            {/* Action Buttons */}
                                            <div className="pt-2 space-y-2">
                                                {/* Download Original */}
                                                {clip.download_url && (
                                                    <a
                                                        href={clip.download_url}
                                                        download={clip.filename}
                                                        className="w-full bg-secondary hover:bg-slate-700 text-white text-sm font-medium py-2 rounded-lg transition-colors flex items-center justify-center gap-2"
                                                    >
                                                        <Download className="w-4 h-4" />
                                                        Download Original
                                                    </a>
                                                )}

                                                {/* Convert to Shorts / Download Shorts */}
                                                {shortsUrls[clip.id] ? (
                                                    <a
                                                        href={shortsUrls[clip.id]}
                                                        download={`shorts_${clip.filename}`}
                                                        className="w-full bg-gradient-to-r from-pink-500 to-orange-500 hover:from-pink-600 hover:to-orange-600 text-white text-sm font-medium py-2 rounded-lg transition-all flex items-center justify-center gap-2"
                                                    >
                                                        <Smartphone className="w-4 h-4" />
                                                        Download Shorts (9:16)
                                                    </a>
                                                ) : (
                                                    <button
                                                        onClick={() => handleConvertToShorts(clip.id)}
                                                        disabled={convertingClips.has(clip.id)}
                                                        className="w-full bg-gradient-to-r from-pink-500 to-orange-500 hover:from-pink-600 hover:to-orange-600 disabled:opacity-50 text-white text-sm font-medium py-2 rounded-lg transition-all flex items-center justify-center gap-2"
                                                    >
                                                        {convertingClips.has(clip.id) ? (
                                                            <>
                                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                                Converting...
                                                            </>
                                                        ) : (
                                                            <>
                                                                <Smartphone className="w-4 h-4" />
                                                                Convert to Shorts (9:16)
                                                            </>
                                                        )}
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </main>
    );
}
