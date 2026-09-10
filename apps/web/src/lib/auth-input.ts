import { z } from "zod";

export const signInInput = z.object({
  email: z.email().max(254).transform(value => value.trim().toLowerCase()),
  password: z.string().min(12, "Use at least 12 characters.").max(128),
});
export const signUpInput = signInInput.extend({
  name: z.string().trim().min(2, "Enter your name.").max(80),
});
