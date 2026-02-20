"use client";

import { useState } from "react";
import { trpc } from "@/lib/trpc/client";
import { EventCard, type EventListItem } from "./event-card";
import { EventDetail } from "./event-detail";

type Group = {
    label: string;
    events: EventListItem[];
};

function getEarliestDate(dates: string[] | null): string | null {
    if (!dates || dates.length === 0) return null;
    return [...dates].sort()[0];
}

function groupEvents(events: EventListItem[]): Group[] {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const upcoming: EventListItem[] = [];
    const pastMap: Map<string, EventListItem[]> = new Map();

    for (const ev of events) {
        const earliest = getEarliestDate(ev.eventDates);
        if (!earliest) {
            // No date → treat as upcoming
            upcoming.push(ev);
            continue;
        }
        const dt = new Date(earliest + "T00:00:00");
        if (dt >= today) {
            upcoming.push(ev);
        } else {
            const key = dt.toLocaleDateString("en-US", {
                month: "long",
                year: "numeric",
            });
            if (!pastMap.has(key)) pastMap.set(key, []);
            pastMap.get(key)!.push(ev);
        }
    }

    const groups: Group[] = [];

    if (upcoming.length > 0) {
        // Sort upcoming: nearest first
        upcoming.sort((a, b) => {
            const da = getEarliestDate(a.eventDates) ?? "9999";
            const db = getEarliestDate(b.eventDates) ?? "9999";
            return da.localeCompare(db);
        });
        groups.push({ label: "Upcoming", events: upcoming });
    }

    // Sort past months: newest month first
    const sortedPastEntries = [...pastMap.entries()].sort((a, b) => {
        const da = getEarliestDate(a[1][0].eventDates) ?? "";
        const db = getEarliestDate(b[1][0].eventDates) ?? "";
        return db.localeCompare(da); // descending
    });

    for (const [label, evs] of sortedPastEntries) {
        // Within a past group: sort descending (most recent first)
        evs.sort((a, b) => {
            const da = getEarliestDate(a.eventDates) ?? "";
            const db = getEarliestDate(b.eventDates) ?? "";
            return db.localeCompare(da);
        });
        groups.push({ label, events: evs });
    }

    return groups;
}

export function Timeline() {
    const { data, isLoading, error } = trpc.events.list.useQuery();
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const [sheetOpen, setSheetOpen] = useState(false);

    const handleCardClick = (id: number) => {
        setSelectedId(id);
        setSheetOpen(true);
    };

    const handleSheetClose = (open: boolean) => {
        setSheetOpen(open);
        if (!open) setSelectedId(null);
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-48 text-neutral-400 text-sm">
                Loading events…
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-48 text-red-400 text-sm">
                Failed to load events. Is the database running?
            </div>
        );
    }

    const events = (data ?? []) as EventListItem[];
    const groups = groupEvents(events);

    if (groups.length === 0) {
        return (
            <div className="flex items-center justify-center h-48 text-neutral-400 text-sm">
                No events to show yet.
            </div>
        );
    }

    return (
        <>
            <div className="flex flex-col gap-8">
                {groups.map((group) => (
                    <section key={group.label}>
                        {/* Group header */}
                        <div className="flex items-center gap-3 mb-4">
                            <span
                                className={
                                    group.label === "Upcoming"
                                        ? "text-sm font-semibold text-neutral-900"
                                        : "text-sm font-medium text-neutral-400"
                                }
                            >
                                {group.label}
                            </span>
                            <div className="flex-1 h-px bg-neutral-100" />
                        </div>

                        {/* Event cards */}
                        <ul className="flex flex-col gap-3">
                            {group.events.map((ev) => (
                                <li key={ev.id}>
                                    <EventCard
                                        event={ev}
                                        isSelected={ev.id === selectedId}
                                        onClick={() => handleCardClick(ev.id)}
                                    />
                                </li>
                            ))}
                        </ul>
                    </section>
                ))}
            </div>

            <EventDetail
                eventId={selectedId}
                open={sheetOpen}
                onOpenChange={handleSheetClose}
            />
        </>
    );
}
