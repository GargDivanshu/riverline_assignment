import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { getAuth } from "@/lib/auth";
import { WorkspaceView } from "@/components/workspace";

export const dynamic = "force-dynamic";
export default async function WorkspacePage() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login");
  return <WorkspaceView user={{ name: session.user.name, email: session.user.email }} />;
}
