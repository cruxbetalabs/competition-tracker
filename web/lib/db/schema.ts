import {
    pgTable,
    serial,
    text,
    integer,
    boolean,
    timestamp,
    date,
} from "drizzle-orm/pg-core";

// ── organizations ─────────────────────────────────────────────────────────────
export const organizations = pgTable("organizations", {
    id: serial("id").primaryKey(),
    slug: text("slug").notNull().unique(),
    name: text("name").notNull().unique(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// ── gyms ──────────────────────────────────────────────────────────────────────
export const gyms = pgTable("gyms", {
    id: serial("id").primaryKey(),
    slug: text("slug").notNull().unique(),
    name: text("name"),
    address: text("address"),
    city: text("city"),
    organizationId: integer("organization_id").references(() => organizations.id),
    googlePlusCode: text("google_plus_code"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// ── posts ─────────────────────────────────────────────────────────────────────
export const posts = pgTable("posts", {
    id: serial("id").primaryKey(),
    gymId: integer("gym_id").references(() => gyms.id),
    organizationId: integer("organization_id").references(() => organizations.id),
    url: text("url").notNull().unique(),
    platform: text("platform"),
    caption: text("caption"),
    mediaUrls: text("media_urls").array(),
    timestamp: timestamp("timestamp", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// ── events ────────────────────────────────────────────────────────────────────
export const events = pgTable("events", {
    id: serial("id").primaryKey(),
    gymId: integer("gym_id").references(() => gyms.id),
    eventName: text("event_name").notNull(),
    eventDates: date("event_dates").array(),
    discipline: text("discipline"),
    summary: text("summary"),
    mergeReason: text("merge_reason"),
    hidden: boolean("hidden").default(true),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

// ── raw_events ────────────────────────────────────────────────────────────────
export const rawEvents = pgTable("raw_events", {
    id: serial("id").primaryKey(),
    gymId: integer("gym_id").references(() => gyms.id),
    postId: integer("post_id").references(() => posts.id),
    eventId: integer("event_id").references(() => events.id),
    eventName: text("event_name"),
    eventDates: date("event_dates").array(),
    discipline: text("discipline"),
    type: text("type"),
    summary: text("summary"),
    reason: text("reason"),
    datePosted: date("date_posted"),
    platform: text("platform"),
    url: text("url"),
    rawMedia: text("raw_media").array(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});
