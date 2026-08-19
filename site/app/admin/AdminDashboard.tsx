"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Overview = {
  users: number;
  beta_capacity: number;
  outstanding_credits: number;
  models: Array<{ status: string; value: number }>;
  jobs: Array<{ id: string; owner_id: string; kind: string; status: string; error?: string; updated_at: string }>;
};

export function AdminDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/v1/admin/overview", { headers: { accept: "application/json" } })
      .then(async (response) => {
        const body = await response.json() as Overview & { error?: { message?: string } };
        if (!response.ok) throw new Error(body.error?.message || "Could not load operations data.");
        setOverview(body);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return <main className="admin-page">
    <nav><Link className="wordmark" href="/">VOICEPRINT<span className="wordmark-dot">●</span></Link><Link href="/beta">WORKSPACE →</Link></nav>
    <header><p className="eyebrow">PRIVATE BETA / OPERATIONS</p><h1>Twenty-five writers.<br />Every job visible.</h1></header>
    {error ? <section className="admin-error"><b>ACCESS UNAVAILABLE</b><p>{error}</p></section> : !overview ? <p>Loading beta operations…</p> : <>
      <section className="admin-metrics">
        <article><span>WRITERS</span><b>{overview.users}/{overview.beta_capacity}</b></article>
        <article><span>OUTSTANDING CREDITS</span><b>{overview.outstanding_credits}</b></article>
        <article><span>MODELS</span><b>{overview.models.reduce((sum, item) => sum + Number(item.value), 0)}</b></article>
      </section>
      <section className="admin-jobs"><div><span>RECENT JOBS</span><span>{overview.jobs.length} SHOWN</span></div>{overview.jobs.map((job) => <article key={job.id}><b>{job.kind.toUpperCase()}</b><code>{job.id}</code><span>{job.status}</span><time>{new Date(job.updated_at).toLocaleString()}</time>{job.error && <p>{job.error}</p>}</article>)}</section>
    </>}
  </main>;
}
