"use client";

import Image from "next/image";
import { cn, gymAvatarColor, gymInitials } from "@/lib/utils";

const DISCIPLINE_STYLES: Record<string, string> = {
    bouldering: "bg-orange-100 text-orange-700",
    "top-rope": "bg-blue-100 text-blue-700",
    lead: "bg-red-100 text-red-700",
    mixed: "bg-violet-100 text-violet-700",
    speed: "bg-emerald-100 text-emerald-700",
};

export type EventListItem = {
    id: number;
    eventName: string;
    eventDates: string[] | null;
    discipline: string | null;
    summary: string | null;
    gymName: string | null;
    gymSlug: string | null;
    gymCity: string | null;
    firstImage: string | null;
};

function formatDates(dates: string[] | null): string {
    if (!dates || dates.length === 0) return "Date TBD";
    const sorted = [...dates].sort();
    const fmt = (d: string) => {
        const dt = new Date(d + "T00:00:00");
        return dt.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            weekday: "short",
        });
    };
    if (sorted.length === 1) return fmt(sorted[0]);
    // Multi-day: show range
    const first = new Date(sorted[0] + "T00:00:00");
    const last = new Date(sorted[sorted.length - 1] + "T00:00:00");
    if (first.getMonth() === last.getMonth()) {
        return `${first.toLocaleDateString("en-US", { month: "short", day: "numeric" })}–${last.getDate()}`;
    }
    return `${first.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${last.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

interface EventCardProps {
    event: EventListItem;
    isSelected?: boolean;
    onClick?: () => void;
}

export function EventCard({ event, isSelected, onClick }: EventCardProps) {
    const slug = event.gymSlug ?? "";
    const avatarColor = gymAvatarColor(slug);
    const initials = gymInitials(event.gymName);
    const disciplineStyle =
        event.discipline ? DISCIPLINE_STYLES[event.discipline] ?? "bg-neutral-100 text-neutral-600" : null;

    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "w-full text-left flex gap-4 rounded-xl border px-4 py-4 transition-all duration-150",
                "hover:border-neutral-300 hover:shadow-sm",
                isSelected
                    ? "border-neutral-900 bg-neutral-50 shadow-sm"
                    : "border-neutral-200 bg-white"
            )}
        >
            {/* Thumbnail */}
            <div className="shrink-0 w-[76px] h-[76px] rounded-lg overflow-hidden">
                {event.firstImage ? (
                    <Image
                        src={event.firstImage}
                        alt={event.eventName}
                        width={76}
                        height={76}
                        unoptimized
                        className="w-full h-full object-cover"
                    />
                ) : (
                    <div
                        className={cn(
                            "w-full h-full flex items-center justify-center text-white font-semibold text-lg",
                            avatarColor
                        )}
                    >
                        {initials}
                    </div>
                )}
            </div>

            {/* Details */}
            <div className="flex-1 min-w-0 flex flex-col gap-1">
                <div className="flex items-start justify-between gap-2">
                    <span className="font-semibold text-sm text-neutral-900 leading-tight line-clamp-2">
                        {event.eventName}
                    </span>
                    {disciplineStyle && (
                        <span
                            className={cn(
                                "shrink-0 text-xs font-medium px-2 py-0.5 rounded-full capitalize",
                                disciplineStyle
                            )}
                        >
                            {event.discipline}
                        </span>
                    )}
                </div>

                <span className="text-xs text-neutral-500">
                    {event.gymName ?? slug}
                    {event.gymCity ? ` · ${event.gymCity}` : ""}
                </span>

                <span className="text-xs font-medium text-neutral-700 mt-0.5">
                    {formatDates(event.eventDates)}
                </span>

                {event.summary && (
                    <p className="text-xs text-neutral-500 leading-relaxed line-clamp-2 mt-0.5">
                        {event.summary}
                    </p>
                )}
            </div>
        </button>
    );
}
