import type { Metadata } from "next";

import { AdminDashboard } from "./AdminDashboard";

export const metadata: Metadata = { title: "Voiceprint Beta Operations" };

export default function AdminPage() {
  return <AdminDashboard />;
}
