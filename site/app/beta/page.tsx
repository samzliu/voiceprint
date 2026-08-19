import type { Metadata } from "next";
import { BetaWorkspace } from "./BetaWorkspace";

export const metadata: Metadata = {
  title: "Voiceprint Beta — train your writing model",
  description: "Build a corpus, train a private Voiceprint model, and draft in your own voice.",
};

export const dynamic = "force-dynamic";

export default function BetaPage() {
  return <BetaWorkspace />;
}
