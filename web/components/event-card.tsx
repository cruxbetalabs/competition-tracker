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
                "w-full text-left rounded-xl border px-4 py-4 transition-all duration-150",
                "hover:border-neutral-300 hover:shadow-lg",
                isSelected
                    ? "border-neutral-400 bg-neutral-100 shadow-md"
                    : "border-neutral-200 bg-white"
            )}
        >
            {/* ── Mobile layout (hidden on sm+) ── */}
            <div className="flex flex-col gap-2 sm:hidden">
                {/* Two-column: thumbnail + (title + gym/dates) */}
                <div className="flex gap-3">
                    <div className="shrink-0 w-15 h-15 rounded-lg overflow-hidden">
                        {event.firstImage ? (
                            <Image
                                src={event.firstImage}
                                alt={event.eventName}
                                width={64}
                                height={64}
                                unoptimized
                                className="w-full h-full object-cover"
                            />
                        ) : (
                            <div
                                className={cn(
                                    "w-full h-full flex items-center justify-center text-white font-semibold text-base",
                                    avatarColor
                                )}
                            >
                                {initials}
                            </div>
                        )}
                    </div>
                    <div className="flex-1 min-w-0 flex flex-col gap-1">
                        <span className="font-semibold text-base text-neutral-900 leading-tight line-clamp-2">
                            {event.eventName}
                        </span>
                        {/* Gym name · city and dates row */}
                        <span className="text-xs text-neutral-600">
                            {event.gymName ?? slug}
                            {event.gymCity && (
                                <span><span className="px-1">·</span>{event.gymCity}</span>
                            )}
                        </span>
                        <span className="text-xs text-neutral-600">
                            {formatDates(event.eventDates)}
                        </span>
                    </div>
                </div>

                <Separator className="mt-1" />

                {/* Summary */}
                {event.summary && (
                    <p className="text-xs text-neutral-600 leading-relaxed line-clamp-2">
                        {event.summary}
                    </p>
                )}

                {/* Badge */}
                {event.discipline && (
                    <div>
                        <Badge variant="secondary" className="capitalize">
                            {event.discipline}
                        </Badge>
                    </div>
                )}
            </div>

            {/* ── Desktop layout (hidden below sm) ── */}
            <div className="hidden sm:flex gap-4">
                {/* Thumbnail */}
                <div className="shrink-0 w-[104px] h-[104px] rounded-lg overflow-hidden">
                    {event.firstImage ? (
                        <Image
                            src={event.firstImage}
                            alt={event.eventName}
                            width={104}
                            height={104}
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
                <div className="flex-1 min-w-0 flex flex-col gap-y-1">
                    <div className="flex items-start justify-between">
                        <span className="font-semibold text-base text-neutral-900 leading-tight line-clamp-2">
                            {event.eventName}
                        </span>
                        {event.discipline && (
                            <Badge variant="secondary" className="capitalize">
                                {event.discipline}
                            </Badge>
                        )}
                    </div>

                    <div className="flex items-start justify-between pr-1 mt-0.5">
                        <span className="text-xs text-neutral-600">
                            {event.gymName ?? slug}
                            {event.gymCity ?
                                <span><span className="px-1">·</span>{event.gymCity}</span> :
                                ""
                            }
                        </span>
                        <span className="text-xs text-neutral-600 mt-0.5">
                            {formatDates(event.eventDates) ? `${formatDates(event.eventDates)}` : ""}
                        </span>
                    </div>

                    <Separator className="my-1" />

                    {event.summary && (
                        <p className="text-xs text-neutral-600 leading-relaxed line-clamp-2 mt-0.5">
                            {event.summary}
                        </p>
                    )}
                </div>
            </div>
        </button>
    );
}
