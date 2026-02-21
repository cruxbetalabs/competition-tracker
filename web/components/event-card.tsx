"use client";

import Image from "next/image";
import { cn, gymAvatarColor, gymInitials } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Separator } from "./ui/separator";

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

    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "w-full text-left flex gap-4 rounded-xl border px-4 py-4 transition-all duration-150",
                "hover:border-neutral-300 hover:shadow-md",
                isSelected
                    ? "border-neutral-900 bg-neutral-50 shadow-md"
                    : "border-neutral-200 bg-white"
            )}
        >
            {/* Thumbnail */}
            <div className="shrink-0 w-[98px] h-[98px] rounded-lg overflow-hidden">
                {event.firstImage ? (
                    <Image
                        src={event.firstImage}
                        alt={event.eventName}
                        width={98}
                        height={98}
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
            <div className="flex-1 min-w-0 flex flex-col gap-y-1.5">
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm text-neutral-900 leading-tight line-clamp-2">
                        {event.eventName}
                    </span>
                    {event.discipline && (
                        <Badge variant="secondary" className="capitalize">
                            {event.discipline}
                        </Badge>
                    )}
                </div>

                <div className="flex items-start justify-between">
                    <span className="text-xs text-neutral-600">
                        {event.gymName ?? slug}
                        {formatDates(event.eventDates) ? ` · ${formatDates(event.eventDates)}` : ""}
                    </span>
                    <span className="text-xs text-neutral-600 mt-0.5">
                        {event.gymCity ?? ""}
                    </span>
                </div>

                <Separator className="my-1" />

                {event.summary && (
                    <p className="text-xs text-neutral-600 leading-relaxed line-clamp-2 mt-0.5">
                        {event.summary}
                    </p>
                )}
            </div>
        </button>
    );
}
