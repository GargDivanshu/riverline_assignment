import { Waves } from "lucide-react";
import { cn } from "@/lib/utils";

export function Brand({ light = false }: { light?: boolean }) {
  return <div className={cn("brand", light && "brand-light")}><span className="brand-icon"><Waves size={23} strokeWidth={2.2} /></span><span>riverline<span className="brand-dot">.</span></span></div>;
}
