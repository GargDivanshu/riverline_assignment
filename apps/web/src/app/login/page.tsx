import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getAuth } from "@/lib/auth";
import { googleEnabled } from "@/lib/env";
import { AuthForm } from "@/components/auth-form";
import { Brand } from "@/components/brand";
import { ArrowUpRight, AudioLines, CalendarDays, Check } from "lucide-react";

export const dynamic = "force-dynamic";
export default async function LoginPage() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (session) redirect("/workspace");
  return <main className="auth-layout">
    <section className="auth-story" aria-label="About Riverline">
      <Brand light />
      <div className="story-main"><span className="eyebrow light">A LITTLE CLARITY GOES A LONG WAY</span>
        <h1>Your money.<br />Your priorities.<br /><span>A clearer plan.</span></h1>
        <p>Make room for what matters, with a practical plan for the next 30 days.</p>
        <div className="story-preview" aria-label="How planning works">
          <div className="story-preview-header"><AudioLines size={19} /><span>A conversation, not a spreadsheet.</span></div>
          <div className="story-step"><span className="step-number">01</span><span>Tell us what’s coming in</span><Check size={16} /></div>
          <div className="story-step"><span className="step-number">02</span><span>Make space for your commitments</span><Check size={16} /></div>
          <div className="story-step"><span className="step-number">03</span><span>See your next steps, clearly</span><ArrowUpRight size={16} /></div>
        </div>
      </div>
      <div className="story-footer"><CalendarDays size={16} /><span>One month at a time. On your terms.</span></div>
    </section>
    <section className="auth-form-side"><div className="mobile-brand"><Brand /></div><AuthForm googleEnabled={googleEnabled()} /><p className="auth-bottom">Clarity starts with a conversation.</p></section>
  </main>;
}
