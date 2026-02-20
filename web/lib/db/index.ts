import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "./schema";

const pool = new Pool({
    host: process.env.DB_HOST ?? "localhost",
    port: parseInt(process.env.DB_PORT ?? "5432"),
    database: process.env.DB_NAME ?? "competition_tracker",
    user: process.env.DB_USER ?? "crux",
    password: process.env.DB_PASSWORD ?? "crux_local",
});

export const db = drizzle(pool, { schema });
