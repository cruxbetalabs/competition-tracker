"use client";

import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, gymAvatarColor, gymInitials } from "@/lib/utils";
import { trpc } from "@/lib/trpc/client";
import { ExternalLink, MapPin, CalendarDays, Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const PLATFORM_LABELS: Record<string, string> = {
    instagram: "Instagram",
    website: "Website",
};

function formatFullDate(d: string): string {
    return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
    });
}

function formatDate(d: string | null): string {
    if (!d) return "—";
    return new Date(d + "T00:00:00").toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function formatDatesRange(dates: string[] | null): string[] {
    if (!dates || dates.length === 0) return ["Date TBD"];
    return [...dates].sort().map(formatFullDate);
}

interface EventDetailProps {
    eventId: number | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function EventDetail({ eventId, open, onOpenChange }: EventDetailProps) {
    const { data: event, isLoading } = trpc.events.getById.useQuery(
        { id: eventId! },
        { enabled: eventId !== null }
    );

    const avatarColor = gymAvatarColor(event?.gymSlug ?? "");
    const initials = gymInitials(event?.gymName);

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent
                side="right"
                className="w-full sm:max-w-lg p-0 flex flex-col"
            >
                {isLoading || !event ? (
                    <div className="flex-1 flex flex-col">
                        <SheetHeader className="sr-only">
                            <SheetTitle>Event details</SheetTitle>
                            <SheetDescription>Loading event information</SheetDescription>
                        </SheetHeader>
                        <div className="flex-1 flex items-center justify-center text-neutral-400 text-sm">
                            {isLoading ? "Loading…" : "Event not found"}
                        </div>
                    </div>
                ) : (
                    <ScrollArea className="flex-1 h-full">
                        <div className="p-6 flex flex-col gap-5">
                            {/* Header */}
                            <SheetHeader className="text-left gap-2">
                                {/* Gym avatar row */}
                                <div className="flex items-center gap-2">
                                    <div
                                        className={cn(
                                            "w-6 h-6 rounded-md flex items-center justify-center text-white text-xs font-semibold shrink-0",
                                            avatarColor
                                        )}
                                    >
                                        {initials}
                                    </div>
                                    <span className="text-sm text-neutral-500">
                                        {event.gymName ?? event.gymSlug}
                                    </span>
                                </div>

                                <SheetTitle className="text-2xl font-bold text-neutral-900 leading-snug">
                                    {event.eventName}
                                </SheetTitle>

                                {event.gymCity && (
                                    <SheetDescription className="flex items-center gap-1 text-sm text-neutral-500">
                                        <MapPin className="w-3 h-3 shrink-0" />
                                        {event.gymAddress
                                            ? `${event.gymAddress}, ${event.gymCity}`
                                            : event.gymCity}
                                    </SheetDescription>
                                )}
                            </SheetHeader>

                            <Separator />

                            {/* Meta fields */}
                            <div className="flex flex-col gap-3.5 text-sm">

                                {/* Dates */}
                                {event.eventDates && event.eventDates.length > 0 && (
                                    <div className="flex items-start gap-2">
                                        <CalendarDays className="w-4 h-4 shrink-0 text-neutral-400 mt-0.5" />
                                        <div className="flex flex-col gap-2">
                                            {formatDatesRange(event.eventDates).map((d) => (
                                                <Badge key={d} variant="outline">
                                                    {d}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Discipline */}
                                {event.discipline && (
                                    <div className="flex items-center gap-2">
                                        <Tag className="w-4 h-4 shrink-0 text-neutral-400" />
                                        <Badge variant="secondary" className="capitalize">
                                            {event.discipline}
                                        </Badge>
                                    </div>
                                )}
                            </div>

                            {/* Summary */}
                            {event.summary && (
                                <>
                                    <Separator />
                                    <div className="flex flex-col">
                                        <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                                            Summary
                                        </span>
                                        <p className="mt-3 text-sm text-neutral-700 leading-relaxed">
                                            {event.summary}
                                        </p>
                                    </div>
                                </>
                            )}

                            {/* Sources */}
                            {event.sources && event.sources.length > 0 && (
                                <>
                                    <Separator />
                                    <div className="flex flex-col">
                                        <span className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                                            Updates ({event.sources.length})
                                        </span>
                                        <ul className="flex flex-col mt-3 gap-2">
                                            {event.sources.map((src) => (
                                                <li
                                                    key={src.id}
                                                    className="flex flex-col gap-1.5 rounded-md border hover:border-gray-300 border-gray-100 bg-white px-3 py-2"
                                                >
                                                    <div className="flex items-center justify-between gap-3">
                                                        <div className="flex items-center gap-2 min-w-0 text-xs">
                                                            <span className="text-neutral-700">
                                                                {formatDate(src.datePosted)}
                                                            </span>
                                                            <span className="text-neutral-400 capitalize">
                                                                {PLATFORM_LABELS[src.platform ?? ""] ??
                                                                    src.platform ??
                                                                    "Unknown"}
                                                            </span>
                                                        </div>

                                                        <div className="flex items-center gap-2 shrink-0">
                                                            {src.type && (
                                                                <Badge variant="secondary" className="capitalize">
                                                                    {src.type}
                                                                </Badge>
                                                            )}
                                                            {src.url && (
                                                                <a
                                                                    href={src.url}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="text-neutral-400 hover:text-neutral-700 transition-colors"
                                                                    aria-label="Open source post"
                                                                >
                                                                    <ExternalLink className="w-3.5 h-3.5" />
                                                                </a>
                                                            )}
                                                        </div>
                                                    </div>

                                                    {src.summary && (
                                                        <p className="text-xs text-neutral-500 leading-relaxed line-clamp-2">
                                                            {src.summary}
                                                        </p>
                                                    )}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </>
                            )}
                        </div>
                    </ScrollArea>
                )}
            </SheetContent>
        </Sheet>
    );
}
