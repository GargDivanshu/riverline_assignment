"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight, CalendarDays, Check, ChevronDown, CreditCard, FileText, ListChecks, LogOut, ShieldCheck, Wallet, Wallet2, type LucideIcon } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { Brand } from "./brand";
import { LiveConversation } from "./live-conversation";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { authClient } from "@/lib/auth-client";
import { trpc } from "@/lib/trpc-client";

type Panel = "available" | "income" | "commitments" | "expenses" | "plan" | "trace" | null;
type Fact = { id: string; label: string; amount_paise?: number | null; due_date?: string | null; recurring_day_of_month?: number | null; timing_note?: string | null; min_amount_paise?: number | null; max_amount_paise?: number | null; usable_amount_paise?: number | null; restricted?: boolean };
type PlanEvent = { date: string; label: string; change_paise: number; balance_paise: number };
type WorkspaceState = { opening_cash?: Fact[]; income?: Fact[]; commitments?: Fact[]; expenses?: Fact[]; timeline?: PlanEvent[]; revision?: number; summary?: { first_shortfall_date?: string | null; projected_closing_paise?: number | null; conditional_closing_paise?: number | null } };
type ConversationTrace = { status: string; mode: string; failure_code?: string | null; events?: Array<{ id: number; event_type: string; role?: string | null; content?: string | null; elapsed_ms?: number | null }> };

const panels = {
  available: { title: "Available now", description: "Cash and savings you can use today.", icon: Wallet2, empty: "Nothing recorded yet.", detail: "A savings cap or business cash you said is off-limits stays visible here, just excluded from the plan." },
  income: { title: "Incoming money", description: "Salary, side earnings, or money someone owes you.", icon: ArrowUpRight, empty: "Nothing recorded yet.", detail: "Amounts, arrival dates and uncertainty stay separate, so expected money doesn't get mistaken for money you already have." },
  commitments: { title: "Loans & EMIs", description: "Loan EMIs, credit-card bills, BNPL, and money you owe people.", icon: CreditCard, empty: "Nothing recorded yet.", detail: "Each payment has its own due date. Money owed to a friend or family member belongs here too." },
  expenses: { title: "Everyday essentials", description: "The things you need to make room for.", icon: Wallet, empty: "Nothing recorded yet.", detail: "You can protect an expense or explore a change — nothing is reduced without your agreement." },
  plan: { title: "Your 30-day plan", description: "A practical schedule built around your money and priorities.", icon: CalendarDays, empty: "Your plan hasn't started yet.", detail: "Once enough facts are in, you'll see dated next steps, any uncovered payments, and the numbers behind them." },
  trace: { title: "Conversation trace", description: "What was said and done, in order.", icon: ListChecks, empty: "Nothing recorded yet.", detail: "Audio is not saved. Text turns, tool calls and timings are, so this stays inspectable." },
} as const;

export function WorkspaceView({ user }: { user: { name: string; email: string } }) {
  const router = useRouter();
  const [panel, setPanel] = useState<Panel>(null);
  const [dialog, setDialog] = useState<"privacy" | null>(null);
  const [voiceActive, setVoiceActive] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [accountError, setAccountError] = useState("");
  const state = trpc.workspace.get.useQuery(undefined, { refetchInterval: voiceActive ? 1000 : false });
  const latestConversation = trpc.conversation.latest.useQuery(undefined, { refetchInterval: voiceActive ? 1000 : false });
  const trace = latestConversation.data as ConversationTrace | null | undefined;
  const firstName = user.name.split(" ")[0];
  const activePanel = panel ? panels[panel] : null;
  const data = state.data as WorkspaceState | undefined;
  const hasAnyFacts = Boolean(data && ((data.opening_cash?.length ?? 0) + (data.income?.length ?? 0) + (data.commitments?.length ?? 0) + (data.expenses?.length ?? 0) > 0));
  const voiceMode = hasAnyFacts ? "returning" : "new";

  async function signOut() {
    setSigningOut(true); setAccountError("");
    try { const result = await authClient.signOut(); if (result.error) throw new Error(); router.push("/login"); router.refresh(); }
    catch { setAccountError("Sign-out failed. Please try again."); setSigningOut(false); }
  }

  return <div className="app-shell">
    <header className="app-topbar">
      <Brand />
      <div className="topbar-right">
        <button className="text-link" onClick={() => setPanel("trace")}>View conversation</button>
        <DropdownMenu><DropdownMenuTrigger asChild><button className="account-button" aria-label="Open account menu"><span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span><ChevronDown size={15} /></button></DropdownMenuTrigger><DropdownMenuContent align="end" className="account-menu"><div className="account-info"><strong>{user.name}</strong><span>{user.email}</span></div><DropdownMenuItem onClick={() => setDialog("privacy")}><ShieldCheck size={16} />About your data</DropdownMenuItem><DropdownMenuItem onClick={signOut} disabled={signingOut}><LogOut size={16} />{signingOut ? "Signing out…" : "Sign out"}</DropdownMenuItem></DropdownMenuContent></DropdownMenu>
      </div>
    </header>
    {(state.error || accountError) && <div className="workspace-alert" role="alert"><span>{accountError || state.error?.message}</span>{state.error && <button onClick={() => state.refetch()}>Try again</button>}</div>}
    <main className="app-main">
      <section className="voice-column">
        <p className="voice-greeting">Hi {firstName} — let&apos;s look at your next 30 days.</p>
        <LiveConversation onActiveChange={setVoiceActive} mode={voiceMode} />
      </section>
      <section className="cards-column">
        <CashflowStrip data={data} />
        <div className="money-grid">
          {(["available", "income", "commitments", "expenses"] as const).map(key => <MoneyCard key={key} panelKey={key} data={data} onOpen={() => setPanel(key)} />)}
        </div>
        <PlanPreview data={data} onOpen={() => setPanel("plan")} />
      </section>
    </main>
    <Sheet open={Boolean(panel)} onOpenChange={open => { if (!open) setPanel(null); }}><SheetContent className="detail-sheet">{activePanel && <><SheetHeader><SheetTitle>{activePanel.title}</SheetTitle><SheetDescription>{activePanel.description}</SheetDescription></SheetHeader>{panel === "trace" ? <TraceList trace={trace} /> : <FactList panel={panel} data={data} empty={activePanel.empty} detail={activePanel.detail} Icon={activePanel.icon} />}</>}</SheetContent></Sheet>
    <Dialog open={dialog === "privacy"} onOpenChange={open => { if (!open) setDialog(null); }}><DialogContent className="info-dialog"><DialogHeader><DialogTitle>Your information, your choices.</DialogTitle><DialogDescription>Financial facts are saved in this local workspace. No bank accounts are connected.</DialogDescription></DialogHeader><div className="dialog-points">{["No bank accounts are connected", "The app does not save audio recordings", "Google sign-in is optional when available"].map(text => <div key={text}><Check size={16} /><span>{text}</span></div>)}</div><Button onClick={() => setDialog(null)}>Back to workspace</Button></DialogContent></Dialog>
  </div>;
}

function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)); }
function formatInr(paise: number) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(paise / 100); }

function factsFor(key: "available" | "income" | "commitments" | "expenses", data: WorkspaceState | undefined): Fact[] {
  if (key === "available") return data?.opening_cash ?? [];
  if (key === "income") return data?.income ?? [];
  if (key === "commitments") return data?.commitments ?? [];
  return data?.expenses ?? [];
}

function CashflowStrip({ data }: { data: WorkspaceState | undefined }) {
  const income = data?.income ?? [];
  const outgoing = [...(data?.commitments ?? []), ...(data?.expenses ?? [])];
  if (!income.length && !outgoing.length) return null;
  const inTotal = income.reduce((sum, fact) => sum + (fact.amount_paise ?? 0), 0);
  const outTotal = outgoing.reduce((sum, fact) => sum + (fact.amount_paise ?? 0), 0);
  const net = inTotal - outTotal;
  return <motion.div className="cashflow-summary" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
    <div className="cashflow-stat"><span>Money in</span><strong>{formatInr(inTotal)}</strong></div>
    <div className="cashflow-stat"><span>Money out</span><strong>{formatInr(outTotal)}</strong></div>
    <div className={`cashflow-stat cashflow-net ${net >= 0 ? "positive" : "negative"}`}><span>Net</span><strong>{formatInr(net)}</strong></div>
  </motion.div>;
}

function MoneyCard({ panelKey, data, onOpen }: { panelKey: "available" | "income" | "commitments" | "expenses"; data: WorkspaceState | undefined; onOpen: () => void }) {
  const item = panels[panelKey];
  const Icon = item.icon;
  const facts = factsFor(panelKey, data);
  const usable = facts.reduce((sum, fact) => sum + (fact.restricted ? 0 : (fact.usable_amount_paise ?? fact.amount_paise ?? 0)), 0);
  const restrictedCount = facts.filter(fact => fact.restricted).length;
  return <motion.button className="money-card" onClick={onOpen} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
    <div className="money-card-top"><span className="metric-icon"><Icon size={18} /></span><ArrowUpRight size={16} className="card-arrow" /></div>
    <h3>{item.title}</h3>
    <span className={facts.length ? "card-amount" : "empty-amount"}>{facts.length ? formatInr(usable) : "—"}</span>
    <div className="money-card-footer">
      <span>{facts.length ? `${facts.length} saved ${facts.length === 1 ? "item" : "items"}${restrictedCount ? ` · ${restrictedCount} restricted` : ""}` : "Nothing yet"}</span>
      <span className="small-plus">+</span>
    </div>
  </motion.button>;
}

function PlanPreview({ data, onOpen }: { data: WorkspaceState | undefined; onOpen: () => void }) {
  const summary = data?.summary;
  const headline = summary?.first_shortfall_date
    ? `A shortfall may land around ${formatDate(summary.first_shortfall_date)}.`
    : summary?.projected_closing_paise != null
      ? `Projected 30-day balance: ${formatInr(summary.projected_closing_paise)}.`
      : "Your plan will build as you talk.";
  return <motion.button className="plan-preview" onClick={onOpen} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05 }}>
    <div className="plan-preview-icon"><FileText size={18} /></div>
    <div><h3>{headline}</h3><p>See the full 30-day view</p></div>
    <ArrowRight size={16} />
  </motion.button>;
}

function FactList({ panel, data, empty, detail, Icon }: { panel: Panel; data: WorkspaceState | undefined; empty: string; detail: string; Icon: LucideIcon }) {
  const facts: Array<Fact | PlanEvent> = panel === "plan" ? data?.timeline ?? [] : panel && panel !== "trace" ? factsFor(panel, data) : [];
  if (!facts.length) return <div className="sheet-empty"><Icon size={30} /><h3>{empty}</h3><p>{detail}</p></div>;
  return <div className="sheet-list">
    <AnimatePresence initial={false}>
      {facts.map(fact => {
        const key = "id" in fact ? fact.id : `${fact.date}-${fact.label}`;
        const amount = "change_paise" in fact ? fact.change_paise : fact.amount_paise ?? 0;
        const isRange = "min_amount_paise" in fact && fact.min_amount_paise != null && fact.max_amount_paise != null;
        return <motion.div key={key} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="sheet-row">
          <div>
            <strong>{fact.label}</strong>
            <p>{"recurring_day_of_month" in fact && fact.recurring_day_of_month ? `Every month on day ${fact.recurring_day_of_month}` : "due_date" in fact && fact.due_date ? formatDate(fact.due_date) : "date" in fact ? formatDate(fact.date) : "Date to confirm"}{"timing_note" in fact && fact.timing_note ? ` · ${fact.timing_note}` : ""}</p>
            {"restricted" in fact && fact.restricted && <span className="fact-badge restricted">Restricted</span>}
            {"usable_amount_paise" in fact && fact.usable_amount_paise != null && !fact.restricted && <span className="fact-badge capped">Usable cap {formatInr(fact.usable_amount_paise)}</span>}
          </div>
          <strong>{isRange && "min_amount_paise" in fact ? `${formatInr(fact.min_amount_paise!)}–${formatInr(fact.max_amount_paise!)}` : formatInr(Math.abs(amount))}</strong>
        </motion.div>;
      })}
    </AnimatePresence>
  </div>;
}

function TraceList({ trace }: { trace: ConversationTrace | null | undefined }) {
  if (!trace?.events?.length) return <div className="sheet-empty"><ListChecks size={30} /><h3>Nothing recorded yet.</h3><p>Your next call&apos;s turns and tool calls will appear here.</p></div>;
  return <div className="sheet-list">
    {trace.events.map(event => <div key={event.id} className="sheet-row trace-row">
      <div><strong>{event.role ?? event.event_type}</strong><p>{event.content ?? event.event_type}</p></div>
      {event.elapsed_ms != null && <span className="trace-time">{(event.elapsed_ms / 1000).toFixed(1)}s</span>}
    </div>)}
    {trace.failure_code && <p className="voice-error">Failure: {trace.failure_code}</p>}
  </div>;
}
