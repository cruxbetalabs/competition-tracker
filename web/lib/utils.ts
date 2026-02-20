import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// ── Gym avatar helpers ─────────────────────────────────────────────────────────

const AVATAR_COLORS = [
    "bg-rose-500",
    "bg-orange-500",
    "bg-amber-500",
    "bg-emerald-500",
    "bg-teal-500",
    "bg-blue-500",
    "bg-violet-500",
    "bg-pink-500",
];

/** Pick a stable color for a gym based on its slug. */
export function gymAvatarColor(slug: string): string {
    let hash = 0;
    for (const c of slug) hash = (hash * 31 + c.charCodeAt(0)) & 0xffffffff;
    return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

/** Extract initials from a gym name (up to 2 letters). */
export function gymInitials(name: string | null | undefined): string {
    if (!name) return "?";
    const words = name.trim().split(/\s+/);
    if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
    return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}
