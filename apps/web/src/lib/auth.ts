import { betterAuth } from "better-auth";
import { getPool } from "./db";
import { googleEnabled, requiredEnv } from "./env";

function createAuth() {
  return betterAuth({
    appName: "Riverline",
    baseURL: process.env.BETTER_AUTH_URL ?? "http://localhost:3000",
    secret: requiredEnv("BETTER_AUTH_SECRET"),
    database: getPool(),
    trustedOrigins: [process.env.APP_ORIGIN ?? "http://localhost:3000"],
    emailAndPassword: { enabled: true, minPasswordLength: 12, maxPasswordLength: 128 },
    account: { accountLinking: { enabled: false } },
    session: { expiresIn: 60 * 60 * 24 * 7, updateAge: 60 * 60 * 24 },
    rateLimit: {
      enabled: true,
      storage: "database",
      window: 60,
      max: 60,
      customRules: {
        "/sign-in/email": { window: 60, max: 5 },
        "/sign-up/email": { window: 60, max: 5 },
      },
    },
    socialProviders: googleEnabled() ? {
      google: {
        clientId: requiredEnv("GOOGLE_CLIENT_ID"),
        clientSecret: requiredEnv("GOOGLE_CLIENT_SECRET"),
      },
    } : {},
  });
}

let auth: ReturnType<typeof createAuth> | undefined;
export function getAuth() { return auth ??= createAuth(); }
