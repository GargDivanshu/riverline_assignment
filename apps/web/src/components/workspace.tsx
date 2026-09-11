"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDownLeft, ArrowRight, ArrowUpRight, AudioLines, CalendarDays, Check, ChevronDown, CircleHelp, CreditCard, FileText, LayoutDashboard, LoaderCircle, LogOut, Mic, MoreHorizontal, ShieldCheck, Wallet } from "lucide-react";
import { motion } from "motion/react";
import { Brand } from "./brand";
import { VoiceOrb } from "./voice-orb";
import { LiveConversation } from "./live-conversation";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { authClient } from "@/lib/auth-client";
import { trpc } from "@/lib/trpc-client";

type Panel = "income" | "commitments" | "expenses" | "plan" | null;
const panels = {
  income: { title: "Incoming money", description: "Salary, side earnings, or money someone owes you.", icon: ArrowDownLeft, empty: "Your income sources will appear here.", detail: "Amounts, arrival dates and uncertainty will stay separate, so expected money doesn’t get mistaken for money you already have." },
  commitments: { title: "Upcoming commitments", description: "Loan payments, card bills, and personal borrowing.", icon: CreditCard, empty: "No commitments added yet.", detail: "Each payment will have its own due date. Money owed to a friend or family member belongs here too." },
  expenses: { title: "Everyday essentials", description: "The things you need to make room for.", icon: Wallet, empty: "Your everyday expenses will appear here.", detail: "You can keep an expense protected or choose to explore a change. Nothing is reduced without your agreement." },
  plan: { title: "Your 30-day plan", description: "A practical schedule built around your money and priorities.", icon: CalendarDays, empty: "Your plan hasn’t started yet.", detail: "Once your conversation is connected, you’ll see dated next steps, any uncovered payments, and the numbers behind them." },
};

export function WorkspaceView({ user }: { user: { name: string; email: string } }) {
  const router = useRouter();
  const [panel, setPanel] = useState<Panel>(null);
  const [dialog, setDialog] = useState<"voice" | "privacy" | null>(null);
  const [voiceActive, setVoiceActive] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [accountError, setAccountError] = useState("");
  const state = trpc.workspace.get.useQuery();
  const firstName = user.name.split(" ")[0];
  const activePanel = panel ? panels[panel] : null;
  const dateLabel = state.data ? `${formatDate(state.data.window_start)} – ${formatDate(previousDate(state.data.window_end_exclusive))}` : "Next 30 days";
  async function signOut() {
    setSigningOut(true); setAccountError("");
    try { const result = await authClient.signOut(); if (result.error) throw new Error(); router.push("/login"); router.refresh(); }
    catch { setAccountError("Sign-out failed. Please try again."); setSigningOut(false); }
  }

  return <div className="workspace-shell">
    <aside className="sidebar"><Brand /><div className="sidebar-body"><span className="nav-label">YOUR WORKSPACE</span><nav aria-label="Main navigation"><button className="nav-item active" aria-current="page"><LayoutDashboard size={18} />Overview</button><button className="nav-item" onClick={() => setPanel("plan")}><CalendarDays size={18} />Your plan</button><button className="nav-item" onClick={() => setPanel("commitments")}><Wallet size={18} />Money details</button></nav><div className="sidebar-note"><span className="sidebar-note-icon"><AudioLines size={20} /></span><h3>Start with what you know.</h3><p>You don’t need every number to take the first step.</p></div></div><button className="nav-item help-link" onClick={() => setDialog("privacy")}><CircleHelp size={18} />About your workspace<ArrowUpRight size={15} /></button><div className="sidebar-foot">A little more clarity.</div></aside>
    <div className="workspace-body">
      <header className="topbar"><div className="breadcrumb"><span className="mobile-brand"><Brand /></span><span className="desktop-crumb">Workspace <span>/</span> <strong>Overview</strong></span></div><div className="topbar-right"><span className="workspace-badge">Personal workspace</span><DropdownMenu><DropdownMenuTrigger asChild><button className="account-button" aria-label="Open account menu"><span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span><span>{firstName}</span><ChevronDown size={15} /></button></DropdownMenuTrigger><DropdownMenuContent align="end" className="account-menu"><div className="account-info"><strong>{user.name}</strong><span>{user.email}</span></div><DropdownMenuItem onClick={() => setDialog("privacy")}><ShieldCheck size={16} />About your data</DropdownMenuItem><DropdownMenuItem onClick={signOut} disabled={signingOut}><LogOut size={16} />{signingOut ? "Signing out…" : "Sign out"}</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div></header>
      <main id="main-content" className="workspace-main">
        <div className="page-heading"><div><span className="eyebrow">LET’S LOOK AHEAD</span><h1>A little clarity, {firstName}.</h1><p>Your money and your next steps, in one place.</p></div><div className="date-range"><CalendarDays size={16} />{dateLabel}</div></div>
        {(state.error || accountError) && <div className="workspace-alert" role="alert"><span>{accountError || state.error?.message}</span>{state.error && <button onClick={() => state.refetch()}>Try again</button>}</div>}
        <motion.section className="conversation-card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <div className="conversation-copy"><span className="section-kicker"><AudioLines size={16} /> YOUR CONVERSATION</span><h2>Let’s make a plan<br />for your next 30 days.</h2><p>Talk through what’s coming in, what’s due,<br className="desktop-break" /> and what matters to you. We’ll take it from there.</p><div className="conversation-actions"><Button className="primary-cta" onClick={() => setDialog("voice")}><Mic size={17} />Start a conversation<ArrowRight size={17} /></Button><span>English · At your pace</span></div></div><div className="conversation-visual"><VoiceOrb /><span className="orb-caption">A clearer path starts here.</span></div>
        </motion.section>
        <div className="section-heading"><h2>Your money at a glance</h2><span>{state.isLoading ? <><LoaderCircle size={14} className="animate-spin" /> Loading workspace</> : "Details will build as you talk"}</span></div>
        <div className="money-grid">{(["income", "commitments", "expenses"] as const).map((key, index) => { const item = panels[key]; const Icon = item.icon; return <motion.button key={key} className="money-card" onClick={() => setPanel(key)} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * index, duration: 0.3 }}><div className="money-card-top"><span className={`metric-icon metric-${key}`}><Icon size={20} /></span><ArrowUpRight size={17} className="card-arrow" /></div><h3>{item.title}</h3><span className="empty-amount" aria-label="Not added yet">—</span><div className="money-card-footer"><span>{key === "income" ? "No income added yet" : key === "commitments" ? "No payments added yet" : "No expenses added yet"}</span><span className="small-plus">+</span></div></motion.button>; })}</div>
        <section className="plan-card"><div className="plan-heading"><div><span className="section-kicker"><CalendarDays size={16} /> YOUR 30-DAY PLAN</span><h2>One step at a time.</h2></div><button className="icon-button" aria-label="View plan details" onClick={() => setPanel("plan")}><MoreHorizontal size={21} /></button></div><div className="plan-placeholder"><div className="plan-placeholder-icon"><FileText size={24} /></div><div><h3>Your next steps will live here.</h3><p>A clear view of what you can pay, when you can pay it,<br className="desktop-break" /> and anything that still needs a little attention.</p></div><Button variant="outline" onClick={() => setPanel("plan")}>Explore your plan<ArrowRight size={16} /></Button></div><div className="plan-footer"><ShieldCheck size={15} /><span>Your priorities come first. Changes are always your choice.</span></div></section>
        <footer className="workspace-footer"><span>Built around your real life.</span><button onClick={() => setDialog("privacy")}>About your data<ArrowUpRight size={13} /></button></footer>
      </main>
    </div>
    <Sheet open={Boolean(panel)} onOpenChange={open => { if (!open) setPanel(null); }}><SheetContent className="detail-sheet">{activePanel && <><SheetHeader><SheetTitle>{activePanel.title}</SheetTitle><SheetDescription>{activePanel.description}</SheetDescription></SheetHeader><div className="sheet-empty"><activePanel.icon size={30} /><h3>{activePanel.empty}</h3><p>{activePanel.detail}</p></div></>}</SheetContent></Sheet>
    <Dialog open={Boolean(dialog)} onOpenChange={open => { if (!open && !voiceActive) setDialog(null); }}><DialogContent className="info-dialog"><DialogHeader><DialogTitle>{dialog === "voice" ? "Your live conversation." : "Your information, your choices."}</DialogTitle><DialogDescription>{dialog === "voice" ? "Speak naturally, pause, and correct yourself whenever you need." : "This version stores your account and sign-in session. Live voice is processed by the configured providers. Financial plans and bank connections are not connected yet."}</DialogDescription></DialogHeader>{dialog === "voice" && <LiveConversation onActiveChange={setVoiceActive} />}<div className="dialog-points">{(dialog === "voice" ? [] : ["No bank accounts are connected", "The app does not save audio recordings", "Google sign-in is optional when available"]).map(text => <div key={text}><Check size={16} /><span>{text}</span></div>)}</div><Button disabled={voiceActive} onClick={() => setDialog(null)}>{voiceActive ? "End the conversation before leaving" : "Back to workspace"}</Button></DialogContent></Dialog>
  </div>;
}

function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)); }
function previousDate(value: string) { const date = new Date(`${value}T00:00:00Z`); date.setUTCDate(date.getUTCDate() - 1); return date.toISOString().slice(0, 10); }
