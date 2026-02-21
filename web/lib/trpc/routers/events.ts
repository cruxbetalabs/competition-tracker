import { z } from "zod";
import { eq, sql, desc } from "drizzle-orm";
import { router, publicProcedure } from "../server";
import { db } from "@/lib/db";
import { events, gyms, rawEvents } from "@/lib/db/schema";

export const eventsRouter = router({
    /**
     * List all visible events, joined with gym info and the first available
     * thumbnail URL from linked raw_events.
     */
    list: publicProcedure.query(async () => {
        const rows = await db
            .select({
                id: events.id,
                eventName: events.eventName,
                eventDates: events.eventDates,
                discipline: events.discipline,
                summary: events.summary,
                createdAt: events.createdAt,
                gymId: events.gymId,
                gymName: gyms.name,
                gymSlug: gyms.slug,
                gymCity: gyms.city,
                firstImage: sql<string | null>`(
          SELECT raw_media[1]
          FROM raw_events
          WHERE event_id = ${events.id}
            AND array_length(raw_media, 1) > 0
          LIMIT 1
        )`.as("first_image"),
            })
            .from(events)
            .leftJoin(gyms, eq(events.gymId, gyms.id))
            .where(eq(events.hidden, false));

        return rows;
    }),

    /**
     * Get a single event by ID with full details and its raw_events list.
     */
    getById: publicProcedure
        .input(z.object({ id: z.number() }))
        .query(async ({ input }) => {
            const [event] = await db
                .select({
                    id: events.id,
                    eventName: events.eventName,
                    eventDates: events.eventDates,
                    discipline: events.discipline,
                    summary: events.summary,
                    mergeReason: events.mergeReason,
                    createdAt: events.createdAt,
                    gymId: events.gymId,
                    gymName: gyms.name,
                    gymSlug: gyms.slug,
                    gymCity: gyms.city,
                    gymAddress: gyms.address,
                })
                .from(events)
                .leftJoin(gyms, eq(events.gymId, gyms.id))
                .where(eq(events.id, input.id))
                .limit(1);

            if (!event) return null;

            const sources = await db
                .select({
                    id: rawEvents.id,
                    platform: rawEvents.platform,
                    datePosted: rawEvents.datePosted,
                    url: rawEvents.url,
                    eventName: rawEvents.eventName,
                    eventDates: rawEvents.eventDates,
                    discipline: rawEvents.discipline,
                    type: rawEvents.type,
                    summary: rawEvents.summary,
                    rawMedia: rawEvents.rawMedia,
                })
                .from(rawEvents)
                .where(eq(rawEvents.eventId, input.id))
                .orderBy(desc(rawEvents.datePosted), desc(rawEvents.id));

            return { ...event, sources };
        }),
});
