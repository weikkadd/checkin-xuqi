import { defineConfig } from "drizzle-kit";
import dotenv from "dotenv";
dotenv.config();

export default defineConfig({
  schema: "./drizzle/schema.ts",
  out: "./drizzle/migrations",
  driver: "mysql2",
  dbCredentials: {
    connectionString: process.env.DATABASE_URL!,
  },
  verbose: true,
  strict: true,
});
